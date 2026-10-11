"""Lets Claude Code on Windows (VS Code, desktop app) use a PHI Protect install inside WSL."""

import os
import platform
import re
import subprocess
from pathlib import Path

WINDOWS_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
COMMAND_TIMEOUT_SECONDS = 15
# Running Windows commands from a WSL folder prints a warning; a Windows folder avoids it.
WINDOWS_WORKING_DIR = "/mnt/c"


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def to_local_path(raw: str) -> Path:
    """Claude Code on Windows reports Windows paths (C:\\..., \\\\wsl.localhost\\...)."""
    if not is_wsl() or not WINDOWS_PATH.match(raw):
        return Path(raw)
    converted = _run(["wslpath", "-u", raw]).strip()
    return Path(converted or raw)


def windows_home() -> Path | None:
    profile = _run(["cmd.exe", "/c", "echo %USERPROFILE%"]).strip()
    if not profile or "%" in profile:
        return None
    return to_local_path(profile)


def windows_claude_version() -> str:
    return _run(["cmd.exe", "/c", "claude --version"])


def bridge_command(python: Path, module: str) -> str:
    """Quotes only values that need it: Windows shells handle nested quotes differently."""
    distro = _quote(os.environ.get("WSL_DISTRO_NAME", ""))
    return f"wsl.exe -d {distro} -e {_quote(python.as_posix())} -m {module} hook"


def _quote(value: str) -> str:
    return f'"{value}"' if any(c.isspace() for c in value) else value


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            cwd=WINDOWS_WORKING_DIR if Path(WINDOWS_WORKING_DIR).is_dir() else None,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""
