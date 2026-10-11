"""Runs the service as a background process on this machine, so users never start it by hand."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".phi-protect"
LOG_FILE = STATE_DIR / "service.log"
PID_FILE = STATE_DIR / "service.pid"
# A start within this window is assumed to still be loading the model, so it is not repeated.
STARTUP_GRACE_SECONDS = 60


def start_in_background() -> bool:
    """Returns True when a start is in progress, i.e. it is worth waiting for the service."""
    if _recently_started():
        return True
    STATE_DIR.mkdir(exist_ok=True)
    # The model is downloaded by `phi-protect setup`; after that the service never goes online.
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "phi_protect.main"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            **_detached(),
        )
    PID_FILE.write_text(str(process.pid))
    return True


def stop() -> bool:
    if not PID_FILE.exists():
        return False
    pid = int(PID_FILE.read_text())
    PID_FILE.unlink()
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def _recently_started() -> bool:
    return PID_FILE.exists() and time.time() - PID_FILE.stat().st_mtime < STARTUP_GRACE_SECONDS


def _detached() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
