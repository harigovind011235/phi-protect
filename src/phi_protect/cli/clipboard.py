"""Puts text on the system clipboard with the operating system's own tool."""

import os
import platform
import shutil
import subprocess
import sys

CLIPBOARD_TIMEOUT_SECONDS = 5


def copy_to_clipboard(text: str) -> bool:
    """Returns False when no clipboard tool works; callers then show the text instead."""
    for command, encoding in _candidates():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(
                command,
                input=text.encode(encoding),
                capture_output=True,
                timeout=CLIPBOARD_TIMEOUT_SECONDS,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        return True
    return False


def _candidates() -> list[tuple[list[str], str]]:
    if sys.platform == "darwin":
        return [(["pbcopy"], "utf-8")]
    if os.name == "nt" or "microsoft" in platform.release().lower():
        # Windows and WSL. clip.exe needs UTF-16 for non-ASCII text, without a byte order mark,
        # which it would paste as a character.
        return [(["clip.exe"], "utf-16-le")]
    return [
        (["wl-copy"], "utf-8"),
        (["xclip", "-selection", "clipboard"], "utf-8"),
        (["xsel", "--clipboard", "--input"], "utf-8"),
    ]
