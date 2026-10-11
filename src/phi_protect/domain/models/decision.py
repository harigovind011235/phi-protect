from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    CANNOT_VERIFY = "cannot_verify"
