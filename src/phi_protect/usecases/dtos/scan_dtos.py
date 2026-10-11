from dataclasses import dataclass, field


@dataclass(frozen=True)
class DetectedEntity:
    entity_type: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class ScanResult:
    has_phi: bool
    entities: list[DetectedEntity] = field(default_factory=list)
    # A suggestion for the user to review, never something to forward automatically.
    deidentified_text: str = ""
