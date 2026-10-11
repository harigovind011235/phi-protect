import json
from pathlib import Path

from phi_protect.cli.claude_settings import (
    hook_command,
    hooks_installed,
    install_hooks,
    settings_path,
    supports_fail_closed,
    uninstall_hooks,
)

COMMAND = hook_command(Path("/opt/phi protect/bin/python"))
EXISTING = {
    "model": "opus",
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "lint"}]}]
    },
}


def write_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(settings))


def test_settings_path_is_global_or_per_project(tmp_path):
    assert settings_path(tmp_path) == tmp_path / ".claude" / "settings.json"
    assert settings_path(None) == Path.home() / ".claude" / "settings.json"


def test_hook_command_quotes_paths_with_spaces():
    assert COMMAND == '"/opt/phi protect/bin/python" -m phi_protect.cli.main hook'


def test_install_keeps_other_settings_and_backs_up(tmp_path):
    path = tmp_path / ".claude" / "settings.json"
    write_settings(path, EXISTING)
    backup = install_hooks(path, COMMAND, fail_closed=False)
    settings = json.loads(path.read_text())
    assert settings["model"] == "opus"
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "lint"
    assert settings["hooks"]["PreToolUse"][1]["matcher"] == "Read"
    assert set(settings["hooks"]) == {"PreToolUse", "SessionStart", "UserPromptSubmit"}
    assert backup is not None and json.loads(backup.read_text()) == EXISTING
    assert hooks_installed(path)


def test_installing_twice_does_not_duplicate(tmp_path):
    path = tmp_path / "settings.json"
    install_hooks(path, COMMAND, fail_closed=False)
    install_hooks(path, COMMAND, fail_closed=False)
    assert len(json.loads(path.read_text())["hooks"]["UserPromptSubmit"]) == 1


def test_fail_closed_only_on_events_that_can_block(tmp_path):
    path = tmp_path / "settings.json"
    install_hooks(path, COMMAND, fail_closed=True)
    hooks = json.loads(path.read_text())["hooks"]
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["onFailure"] == "block"
    assert hooks["PreToolUse"][0]["hooks"][0]["onFailure"] == "block"
    assert "onFailure" not in hooks["SessionStart"][0]["hooks"][0]


def test_uninstall_removes_only_ours(tmp_path):
    path = tmp_path / ".claude" / "settings.json"
    write_settings(path, EXISTING)
    install_hooks(path, COMMAND, fail_closed=False)
    assert uninstall_hooks(path)
    assert json.loads(path.read_text()) == EXISTING
    assert not hooks_installed(path)
    assert not uninstall_hooks(path)


def test_fail_closed_needs_a_recent_claude_code():
    assert supports_fail_closed("2.1.295 (Claude Code)")
    assert supports_fail_closed("2.2.0 (Claude Code)")
    assert not supports_fail_closed("2.1.282 (Claude Code)")
    assert not supports_fail_closed("")
