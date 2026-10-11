from phi_protect.domain.models import Finding, FindingSource

from .allowlist import is_allowed
from .blocking import decide, is_blocking
from .merging import merge_overlaps
from .placeholders import deidentify, placeholders, replace_spans


def resolve_findings(text: str, candidates: list[Finding]) -> list[Finding]:
    """Turns raw candidates from all detectors into the final, non-overlapping findings.

    The allowlist only judges detector guesses, never rule findings, and it runs on each candidate
    before merging, so it can veto one detector's guess but never erase another finding.
    """
    kept = [f for f in candidates if f.source == FindingSource.RULE or not _allowlisted(text, f)]
    return merge_overlaps(kept, text)


def _allowlisted(text: str, finding: Finding) -> bool:
    return is_allowed(text, finding.entity_type, finding.start, finding.end)


__all__ = [
    "decide",
    "deidentify",
    "is_allowed",
    "is_blocking",
    "merge_overlaps",
    "placeholders",
    "replace_spans",
    "resolve_findings",
]
