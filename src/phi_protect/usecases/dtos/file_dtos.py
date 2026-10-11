from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileScanResult:
    decision: str  # "allow", "block" or "cannot_verify"
    file_type: str
    reason: str | None = None
    entity_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DeidentifiedFile:
    content: bytes
    media_type: str
    extension: str
