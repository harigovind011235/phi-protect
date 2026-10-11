"""Adds and removes the PHI Protect hooks in a Claude Code settings.json; nothing else changes."""

import json
import re
import shutil
import subprocess
from pathlib import Path

HOOK_MODULE = "phi_protect.cli.main"
# event -> (tool matcher, timeout in seconds). Timeouts cover the model loading on first use.
HOOK_EVENTS: dict[str, tuple[str | None, int]] = {
    "SessionStart": (None, 30),
    "UserPromptSubmit": (None, 90),
    "PreToolUse": ("Read", 120),
}
# Events that can block. Older Claude Code versions reject the `onFailure` field.
FAIL_CLOSED_EVENTS = {"UserPromptSubmit", "PreToolUse"}
MIN_FAIL_CLOSED_VERSION = (2, 1, 295)
BACKUP_SUFFIX = ".phi-protect-backup"


def settings_path(project: Path | None) -> Path:
    base = project if project else Path.home()
    return base / ".claude" / "settings.json"


def hook_command(python: Path) -> str:
    return f'"{python.as_posix()}" -m {HOOK_MODULE} hook'


def install_hooks(path: Path, command: str, fail_closed: bool) -> Path | None:
    """Returns the backup of the previous settings file, if there was one."""
    settings = _load(path)
    _remove_ours(settings)
    hooks = settings.setdefault("hooks", {})
    for event, (matcher, timeout) in HOOK_EVENTS.items():
        hook: dict = {"type": "command", "command": command, "timeout": timeout}
        if fail_closed and event in FAIL_CLOSED_EVENTS:
            hook["onFailure"] = "block"
        group: dict = {"hooks": [hook]}
        if matcher:
            group["matcher"] = matcher
        hooks.setdefault(event, []).append(group)
    backup = _backup(path)
    _write(path, settings)
    return backup


def uninstall_hooks(path: Path) -> bool:
    if not path.exists():
        return False
    settings = _load(path)
    if not _remove_ours(settings):
        return False
    _backup(path)
    _write(path, settings)
    return True


def hooks_installed(path: Path) -> bool:
    return path.exists() and any(_is_ours(h) for h in _all_hooks(_load(path)))


def claude_version() -> str:
    # shutil.which also finds `claude.cmd`, how npm installs it on Windows.
    executable = shutil.which("claude")
    if executable is None:
        return ""
    try:
        return subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=15, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def supports_fail_closed(version_output: str) -> bool:
    match = re.match(r"\s*(\d+)\.(\d+)\.(\d+)", version_output)
    return bool(match) and tuple(int(part) for part in match.groups()) >= MIN_FAIL_CLOSED_VERSION


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    shutil.copy2(path, backup)
    return backup


def _remove_ours(settings: dict) -> bool:
    removed = False
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        kept_groups = []
        for group in hooks[event]:
            kept = [h for h in group.get("hooks", []) if not _is_ours(h)]
            removed |= len(kept) != len(group.get("hooks", []))
            if kept:
                kept_groups.append({**group, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    return removed


def _all_hooks(settings: dict) -> list[dict]:
    groups = [g for event_groups in settings.get("hooks", {}).values() for g in event_groups]
    return [h for group in groups for h in group.get("hooks", [])]


def _is_ours(hook: dict) -> bool:
    return HOOK_MODULE in hook.get("command", "")
