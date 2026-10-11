"""`.phi-protect-ignore`: repo paths whose file reads are not checked, e.g. fake-patient fixtures.

The file only counts when it is committed to git and unchanged, so every exception is in the repo's
history and goes through code review. Patterns are relative to the folder holding the file; `*`
matches across folders, and a pattern ending in `/` matches everything under that folder.
"""

import subprocess
from fnmatch import fnmatch
from pathlib import Path

IGNORE_FILE_NAME = ".phi-protect-ignore"
GIT_TIMEOUT_SECONDS = 5
# Patterns that would switch the check off for a whole repo.
TOO_BROAD = {"*", "**", "**/*", "*/**", "/", ".", "./"}


def is_ignored(path: Path) -> bool:
    real_path = path.resolve()
    ignore_file = _nearest_ignore_file(real_path.parent)
    if ignore_file is None or not _committed_and_unchanged(ignore_file):
        return False
    try:
        relative = real_path.relative_to(ignore_file.parent.resolve()).as_posix()
    except ValueError:
        return False
    return any(_matches(relative, pattern) for pattern in read_patterns(ignore_file))


def read_patterns(ignore_file: Path) -> list[str]:
    lines = (line.strip() for line in ignore_file.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#") and _allowed(line)]


def _allowed(pattern: str) -> bool:
    return pattern not in TOO_BROAD and not pattern.startswith("/") and ".." not in pattern


def _matches(relative: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        return relative.startswith(pattern)
    return fnmatch(relative, pattern)


def _nearest_ignore_file(folder: Path) -> Path | None:
    for candidate in (folder, *folder.parents):
        ignore_file = candidate / IGNORE_FILE_NAME
        if ignore_file.is_file():
            return ignore_file
    return None


def _committed_and_unchanged(ignore_file: Path) -> bool:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args, "--", ignore_file.name],
            cwd=ignore_file.parent,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )

    try:
        tracked = git("ls-files", "--error-unmatch").returncode == 0
        return tracked and git("status", "--porcelain").stdout.strip() == ""
    except (OSError, subprocess.SubprocessError):
        return False
