import json

import pytest

from phi_protect.cli.hook import HookContext, failed_unexpectedly, handle_event
from phi_protect.cli.service_client import ServiceError

PHI_SCAN = {
    "has_phi": True,
    "entities": [
        {"entity_type": "PERSON", "start": 11, "end": 22, "score": 0.99},
        {"entity_type": "MEMBER_ID", "start": 34, "end": 46, "score": 0.85},
    ],
    "deidentified_text": "Appeal for [PERSON_1], member ID [MEMBER_ID_1]",
}
PHI_FILE = {"decision": "block", "entity_counts": {"PERSON": 1}, "reason": None}
UNCHECKABLE_FILE = {
    "decision": "cannot_verify",
    "entity_counts": {},
    "reason": "page 1 has an image",
}


class FakeClient:
    def __init__(self, running=True, scan=None, file_scan=None, error=None):
        self.running = running
        self.scan = scan or {"has_phi": False, "entities": [], "deidentified_text": ""}
        self.file_scan = file_scan or {"decision": "allow", "entity_counts": {}, "reason": None}
        self.error = error
        self.scanned_files: list[bytes] = []
        self.scanned_texts: list[str] = []
        self.waited = None

    def is_running(self):
        return self.running

    def wait_until_running(self, timeout_seconds):
        self.waited = timeout_seconds
        return self.running

    def scan_text(self, text):
        if self.error:
            raise self.error
        self.scanned_texts.append(text)
        return self.scan

    def scan_file(self, data):
        if self.error:
            raise self.error
        self.scanned_files.append(data)
        return self.file_scan


class FakeOverrides:
    def __init__(self, confirmed=False):
        self.confirmed = confirmed
        self.remembered: list[list[str]] = []

    def remember(self, phi_values):
        self.remembered.append(phi_values)

    def consume(self, phi_values):
        return self.confirmed


def make_context(client=None, mode="block", starting=False, copied=None, overrides=None):
    def copy_text(text):
        if copied is None:
            return False
        copied.append(text)
        return True

    return HookContext(
        client=client or FakeClient(),
        start_service=lambda: starting,
        copy_text=copy_text,
        overrides=overrides or FakeOverrides(),
        mode=mode,
    )


def prompt_event(prompt="Appeal for Maria Lopez, member ID XGH884213901"):
    return {"hook_event_name": "UserPromptSubmit", "prompt": prompt}


def read_event(path, **tool_input):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": str(path), **tool_input},
    }


def permission(outcome) -> tuple[str, str]:
    output = json.loads(outcome.stdout)["hookSpecificOutput"]
    return output["permissionDecision"], output["permissionDecisionReason"]


def message_to_user(outcome) -> str:
    return json.loads(outcome.stdout)["systemMessage"]


def text_file(tmp_path, content="name\nMaria Lopez\n"):
    path = tmp_path / "notes.txt"
    path.write_text(content)
    return path


# Both modes


@pytest.mark.parametrize(("running", "starts"), [(False, 1), (True, 0)])
def test_session_start_starts_the_service_only_when_it_is_not_running(running, starts):
    started = []
    context = HookContext(
        client=FakeClient(running=running),
        start_service=lambda: started.append(1) or True,
        copy_text=lambda _: False,
        overrides=FakeOverrides(),
    )
    assert handle_event({"hook_event_name": "SessionStart"}, context).exit_code == 0
    assert len(started) == starts


@pytest.mark.parametrize("mode", ["warn", "block"])
def test_clean_prompts_and_files_pass_silently(tmp_path, mode):
    context = make_context(mode=mode)
    assert handle_event(prompt_event("How do I paginate a query?"), context).exit_code == 0
    assert handle_event(read_event(text_file(tmp_path, "nothing sensitive")), context).stdout == ""
    assert handle_event(read_event(tmp_path / "missing"), context).stdout == ""


@pytest.mark.parametrize("mode", ["warn", "block"])
def test_flagged_prompt_offers_the_deidentified_version_on_the_clipboard(mode):
    copied = []
    context = make_context(FakeClient(scan=PHI_SCAN), mode, copied=copied)
    outcome = handle_event(prompt_event(), context)
    assert outcome.exit_code == 2
    assert copied == ["Appeal for [PERSON_1], member ID [MEMBER_ID_1]"]
    assert "on your clipboard" in outcome.stderr
    assert "MEMBER_ID: 1, PERSON: 1" in outcome.stderr
    assert "Maria" not in outcome.stderr


def test_only_the_lines_claude_will_read_are_checked(tmp_path):
    path = tmp_path / "big.log"
    path.write_text("".join(f"line {i}\n" for i in range(1, 11)))
    client = FakeClient()
    handle_event(read_event(path, offset=3, limit=2), make_context(client))
    assert client.scanned_files == [b"line 3\nline 4\n"]


def test_other_tools_are_not_checked():
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert handle_event(event, make_context(FakeClient(running=False))).exit_code == 0


@pytest.mark.parametrize(("starting", "expected_wait"), [(True, 60), (False, 3)])
def test_waits_long_only_while_the_service_is_starting(starting, expected_wait):
    client = FakeClient(running=False)
    handle_event(prompt_event(), make_context(client, starting=starting))
    assert client.waited == expected_wait


# Warn mode: a helper; the user decides


def test_warn_flags_a_prompt_once_and_remembers_its_patient_data():
    overrides = FakeOverrides()
    context = make_context(FakeClient(scan=PHI_SCAN), "warn", overrides=overrides)
    outcome = handle_event(prompt_event(), context)
    assert outcome.exit_code == 2
    assert "send it within 5 minutes" in outcome.stderr
    assert "[phi-ok]" in outcome.stderr
    assert overrides.remembered == [["Maria Lopez", "XGH884213901"]]


def test_warn_recognises_resends_by_stable_values_not_generic_ids():
    prompt = '<pasted id="9f31">Appeal for Maria Lopez</pasted id="9f31">'
    scan = {
        "has_phi": True,
        "entities": [
            {"entity_type": "ID", "start": 12, "end": 16, "score": 0.6},
            {"entity_type": "PERSON", "start": 29, "end": 40, "score": 0.99},
        ],
        "deidentified_text": "",
    }
    overrides = FakeOverrides()
    handle_event(
        prompt_event(prompt), make_context(FakeClient(scan=scan), "warn", overrides=overrides)
    )
    assert overrides.remembered == [["Maria Lopez"]]


def test_warn_sends_the_same_patient_data_sent_again():
    context = make_context(FakeClient(scan=PHI_SCAN), "warn", overrides=FakeOverrides(True))
    outcome = handle_event(prompt_event(), context)
    assert outcome.exit_code == 0
    assert "sent as-is" in message_to_user(outcome)


@pytest.mark.parametrize("tag", ["[phi-ok]", "[PHI-OK]"])
def test_warn_sends_a_tagged_prompt_without_checking(tag):
    client = FakeClient(scan=PHI_SCAN)
    outcome = handle_event(
        prompt_event(f"{tag} Appeal for Maria Lopez"), make_context(client, "warn")
    )
    assert outcome.exit_code == 0
    assert "[phi-ok]" in message_to_user(outcome)
    assert client.scanned_texts == []


def test_warn_sends_the_prompt_with_a_warning_when_it_cannot_be_checked():
    outcome = handle_event(prompt_event(), make_context(FakeClient(running=False), "warn"))
    assert outcome.exit_code == 0
    assert "sent unchecked" in message_to_user(outcome)


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (FakeClient(file_scan=PHI_FILE), "PERSON: 1"),
        (FakeClient(file_scan=UNCHECKABLE_FILE), "page 1 has an image"),
        (FakeClient(running=False), "could not check"),
    ],
)
def test_warn_asks_before_reading_a_flagged_file(tmp_path, client, expected):
    outcome = handle_event(read_event(text_file(tmp_path)), make_context(client, "warn"))
    decision, reason = permission(outcome)
    assert decision == "ask"
    assert expected in reason
    assert "Maria" not in reason


def test_warn_continues_after_an_unexpected_error():
    outcome = failed_unexpectedly(ValueError("Maria Lopez"), "warn")
    assert outcome.exit_code == 0
    assert "Maria" not in outcome.stdout


# Block mode: enforcement; fail closed


@pytest.mark.parametrize(
    "client",
    [FakeClient(running=False), FakeClient(error=ServiceError("the service is not reachable"))],
)
def test_block_blocks_a_prompt_that_cannot_be_checked(client):
    outcome = handle_event(prompt_event(), make_context(client, "block"))
    assert outcome.exit_code == 2
    assert "could not check" in outcome.stderr


@pytest.mark.parametrize(
    ("prompt", "overrides"),
    [
        (prompt_event()["prompt"], FakeOverrides(True)),
        ("[phi-ok] " + prompt_event()["prompt"], FakeOverrides()),
    ],
)
def test_block_ignores_resends_and_tags(prompt, overrides):
    context = make_context(FakeClient(scan=PHI_SCAN), "block", overrides=overrides)
    assert handle_event(prompt_event(prompt), context).exit_code == 2


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        (FakeClient(file_scan=PHI_FILE), "PERSON: 1"),
        (FakeClient(file_scan=UNCHECKABLE_FILE), "page 1 has an image"),
        (FakeClient(running=False), "could not be checked"),
    ],
)
def test_block_denies_a_flagged_file(tmp_path, client, expected):
    outcome = handle_event(read_event(text_file(tmp_path)), make_context(client))
    decision, reason = permission(outcome)
    assert decision == "deny"
    assert expected in reason
    assert "Maria" not in reason


def test_block_blocks_after_an_unexpected_error():
    outcome = failed_unexpectedly(ValueError("Maria Lopez"), "block")
    assert outcome.exit_code == 2
    assert "Maria" not in outcome.stderr
