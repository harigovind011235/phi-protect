"""Claude Code hook: checks prompts and file reads with the PHI Protect service before Claude.

Two modes (PHI_MODE):
- warn (default): a helper. Likely PHI is flagged and the user decides: file reads ask for
  permission, a flagged prompt goes through when sent again, and if the check itself fails the user
  is warned but not stopped.
- block: enforcement. PHI, and anything that cannot be checked, is blocked (fail closed).

Messages never contain the detected values, only their types.
"""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from phi_protect.cli.ignore_file import is_ignored
from phi_protect.cli.service_client import ServiceError
from phi_protect.cli.wsl import to_local_path

WARN = "warn"
# Warn mode: a prompt with this tag anywhere is sent without checking. It is not a prefix because
# Claude Code gives a leading #, !, / or @ its own meaning.
APPROVAL_TAG = "[phi-ok]"
# The model's generic guesses change with surrounding noise (e.g. the random IDs chat apps put
# around pastes), so they are left out when recognising the same patient data sent again.
UNSTABLE_TYPES = {"ID", "DATE_TIME"}
PDF_MAGIC = b"%PDF-"
# What Claude Code's Read tool returns when no offset/limit is given.
READ_DEFAULT_LIMIT_LINES = 2000
# The first prompt after a session starts may have to wait for the model to load. When nothing is
# starting, a short wait is enough to decide the service is down.
STARTUP_WAIT_SECONDS = 60
UNAVAILABLE_WAIT_SECONDS = 3

PROMPT_FLAGGED = """PHI Protect: this prompt looks like it contains patient information ({summary}).
It was not sent.

{next_step}
If this is a false alarm: copy your original again and send it within 5 minutes (the same
patient data sent again goes through as-is), or add [phi-ok] anywhere in your prompt.

{deidentified}"""
PROMPT_BLOCKED = """PHI Protect blocked this prompt: it contains patient information ({summary}).
Nothing was sent to Claude.

{next_step}

{deidentified}"""
NEXT_STEP_COPIED = (
    "A de-identified version is on your clipboard: paste it (Ctrl+V / Cmd+V), check it, "
    "and send it."
)
NEXT_STEP_MANUAL = "Review this de-identified version, edit it if needed, and send it instead:"
PROMPT_SENT_AS_IS = "PHI Protect: sent as-is, as you confirmed by sending the same data again."
PROMPT_TAGGED = "PHI Protect: sent without checking, as tagged [phi-ok]."
PROMPT_UNCHECKED_WARNING = (
    "PHI Protect could not check this prompt ({reason}); it was sent unchecked."
)
PROMPT_UNCHECKED = (
    "PHI Protect could not check this prompt ({reason}), so it was not sent. "
    "Check the service with: phi-protect status"
)
FILE_FLAGGED = (
    "PHI Protect: this file looks like it contains patient information ({summary}). "
    "Allow only if this is a false alarm; otherwise deny, and you can make a de-identified copy "
    "with: phi-protect deidentify <file>"
)
FILE_UNCHECKED_QUESTION = (
    "PHI Protect could not check this file ({reason}). Allow only if you know it has no patient "
    "information."
)
FILE_BLOCKED = (
    "PHI Protect blocked reading this file: it contains patient information ({summary}). "
    "Do not try to read it another way, for example with shell commands. Tell the user; they can "
    "create a de-identified copy with: phi-protect deidentify <file>"
)
FILE_UNCHECKABLE = (
    "PHI Protect blocked reading this file: {reason}. Do not try to read it another way, "
    "for example with shell commands. Tell the user."
)


class PhiService(Protocol):
    def is_running(self) -> bool: ...
    def wait_until_running(self, timeout_seconds: float) -> bool: ...
    def scan_text(self, text: str) -> dict: ...
    def scan_file(self, data: bytes) -> dict: ...


class Overrides(Protocol):
    def remember(self, phi_values: list[str]) -> None: ...
    def consume(self, phi_values: list[str]) -> bool: ...


@dataclass(frozen=True)
class HookContext:
    client: PhiService
    start_service: Callable[[], bool]
    copy_text: Callable[[str], bool]
    overrides: Overrides
    mode: str = WARN

    @property
    def warn(self) -> bool:
        return self.mode == WARN


@dataclass(frozen=True)
class HookOutcome:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


def handle_event(event: dict, context: HookContext) -> HookOutcome:
    name = event.get("hook_event_name")
    if name == "SessionStart":
        if not context.client.is_running():
            context.start_service()
        return HookOutcome()
    if name == "UserPromptSubmit":
        return _check_prompt(event.get("prompt", ""), context)
    if name == "PreToolUse" and event.get("tool_name") == "Read":
        return _check_file_read(event.get("tool_input", {}), context)
    return HookOutcome()


def failed_unexpectedly(error: Exception, mode: str) -> HookOutcome:
    """Last line of defence: warn mode lets the user continue, block mode blocks."""
    reason = str(error) if isinstance(error, ServiceError) else type(error).__name__
    message = f"PHI Protect could not run its check ({reason})."
    if mode == WARN:
        return HookOutcome(stdout=_message_to_user(message))
    return HookOutcome(exit_code=2, stderr=message)


def _check_prompt(prompt: str, context: HookContext) -> HookOutcome:
    if context.warn and APPROVAL_TAG in prompt.lower():
        return HookOutcome(stdout=_message_to_user(PROMPT_TAGGED))
    try:
        _ensure_running(context)
        result = context.client.scan_text(prompt)
    except ServiceError as error:
        if context.warn:
            return HookOutcome(
                stdout=_message_to_user(PROMPT_UNCHECKED_WARNING.format(reason=error))
            )
        return HookOutcome(exit_code=2, stderr=PROMPT_UNCHECKED.format(reason=error))
    if not result["has_phi"]:
        return HookOutcome()
    phi_values = _stable_values(prompt, result["entities"])
    if context.warn and context.overrides.consume(phi_values):
        return HookOutcome(stdout=_message_to_user(PROMPT_SENT_AS_IS))

    deidentified = result["deidentified_text"]
    # Replacing the clipboard also drops the original text the user copied, which held the PHI.
    next_step = NEXT_STEP_COPIED if context.copy_text(deidentified) else NEXT_STEP_MANUAL
    summary = _summary(Counter(e["entity_type"] for e in result["entities"]))
    template = PROMPT_FLAGGED if context.warn else PROMPT_BLOCKED
    if context.warn:
        context.overrides.remember(phi_values)
    message = template.format(summary=summary, next_step=next_step, deidentified=deidentified)
    return HookOutcome(exit_code=2, stderr=message)


def _stable_values(prompt: str, entities: list[dict]) -> list[str]:
    stable = [e for e in entities if e["entity_type"] not in UNSTABLE_TYPES] or entities
    return [prompt[e["start"] : e["end"]] for e in stable]


def _check_file_read(tool_input: dict, context: HookContext) -> HookOutcome:
    path = to_local_path(tool_input.get("file_path", ""))
    if not path.is_file() or is_ignored(path):
        return HookOutcome()
    try:
        _ensure_running(context)
        result = context.client.scan_file(_requested_content(path, tool_input))
    except ServiceError as error:
        reason = f"it could not be checked ({error})"
        return _file_decision(context, FILE_UNCHECKED_QUESTION, FILE_UNCHECKABLE, reason=reason)
    if result["decision"] == "allow":
        return HookOutcome()
    if result["decision"] == "cannot_verify":
        reason = result["reason"]
        return _file_decision(context, FILE_UNCHECKED_QUESTION, FILE_UNCHECKABLE, reason=reason)
    summary = _summary(Counter(result["entity_counts"]))
    return _file_decision(context, FILE_FLAGGED, FILE_BLOCKED, summary=summary)


def _file_decision(context: HookContext, ask_text: str, deny_text: str, **values) -> HookOutcome:
    """Warn mode asks the user (Claude Code's permission dialog); block mode denies."""
    if context.warn:
        return _permission("ask", ask_text.format(**values))
    return _permission("deny", deny_text.format(**values))


def _requested_content(path, tool_input: dict) -> bytes:
    """Checks only the lines Claude will receive, so large text files stay readable."""
    data = path.read_bytes()
    if data.startswith(PDF_MAGIC) or b"\x00" in data:
        return data
    first_line = max(int(tool_input.get("offset") or 1), 1) - 1
    limit = int(tool_input.get("limit") or READ_DEFAULT_LIMIT_LINES)
    return b"".join(data.splitlines(keepends=True)[first_line : first_line + limit])


def _ensure_running(context: HookContext) -> None:
    if context.client.is_running():
        return
    wait_seconds = STARTUP_WAIT_SECONDS if context.start_service() else UNAVAILABLE_WAIT_SECONDS
    if not context.client.wait_until_running(wait_seconds):
        raise ServiceError("the PHI Protect service is not running")


def _permission(decision: str, reason: str) -> HookOutcome:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    return HookOutcome(stdout=json.dumps(output))


def _message_to_user(text: str) -> str:
    """Shown to the user by Claude Code without blocking or reaching Claude."""
    return json.dumps({"systemMessage": text})


def _summary(counts: Counter) -> str:
    return ", ".join(f"{entity_type}: {count}" for entity_type, count in sorted(counts.items()))
