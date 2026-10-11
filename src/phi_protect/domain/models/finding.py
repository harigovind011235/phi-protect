from dataclasses import dataclass
from enum import StrEnum

from phi_protect.domain.models.entity_type import EntityType


class FindingSource(StrEnum):
    DETECTOR = "detector"
    RULE = "rule"


@dataclass(frozen=True)
class Finding:
    """A span of text that may be PHI. `end` is exclusive; offsets are Python string positions."""

    entity_type: EntityType
    start: int
    end: int
    score: float
    source: FindingSource = FindingSource.DETECTOR
