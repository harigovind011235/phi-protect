"""Warn mode: sending the same patient data again shortly after means "send it as-is".

A resend is recognised by the detected values (names, IDs, ...), not the exact text: chat apps wrap
pastes in markers with random IDs, so the same content never looks identical twice. Only a salted
fingerprint of those values is kept, never the values, and it is deleted once used or after a few
minutes.
"""

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

OVERRIDE_WINDOW_SECONDS = 300


class PromptOverrides:
    def __init__(self, path: Path):
        self._path = path

    def remember(self, phi_values: list[str]) -> None:
        salt = secrets.token_hex(16)
        record = {
            "salt": salt,
            "digest": _digest(salt, phi_values),
            "expires": time.time() + OVERRIDE_WINDOW_SECONDS,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(record), encoding="utf-8")

    def consume(self, phi_values: list[str]) -> bool:
        """True when this patient data was flagged moments ago and is sent again on purpose."""
        try:
            record = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if time.time() > record.get("expires", 0):
            self._path.unlink(missing_ok=True)
            return False
        if not hmac.compare_digest(
            _digest(record.get("salt", ""), phi_values), record.get("digest", "")
        ):
            return False
        self._path.unlink(missing_ok=True)
        return True


def _digest(salt: str, phi_values: list[str]) -> str:
    canonical = "\n".join(sorted({" ".join(value.lower().split()) for value in phi_values}))
    return hashlib.sha256(f"{salt}:{canonical}".encode()).hexdigest()
