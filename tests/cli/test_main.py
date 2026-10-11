import io
import json
from types import SimpleNamespace

from phi_protect.cli import main as cli
from phi_protect.cli.hook import HookOutcome


def test_hook_reads_and_writes_utf8_whatever_the_console_encoding(monkeypatch):
    received = []

    def fake_handle_event(event, *_):
        received.append(event)
        return HookOutcome(exit_code=2, stderr="Draft for José: [PERSON_1]")

    stdout, stderr = io.BytesIO(), io.BytesIO()
    event = {"hook_event_name": "UserPromptSubmit", "prompt": "José Núñez"}
    monkeypatch.setattr(cli, "handle_event", fake_handle_event)
    monkeypatch.setattr(
        cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(event).encode()))
    )
    monkeypatch.setattr(cli.sys, "stdout", SimpleNamespace(buffer=stdout))
    monkeypatch.setattr(cli.sys, "stderr", SimpleNamespace(buffer=stderr))

    assert cli.main(["hook"]) == 2
    assert received == [event]
    assert stderr.getvalue().decode("utf-8") == "Draft for José: [PERSON_1]"


def test_windows_option_outside_wsl_is_rejected(monkeypatch, capsys):
    monkeypatch.setattr(cli.wsl, "is_wsl", lambda: False)
    assert cli.main(["uninstall", "--windows"]) == 1
    assert "works from WSL only" in capsys.readouterr().out
