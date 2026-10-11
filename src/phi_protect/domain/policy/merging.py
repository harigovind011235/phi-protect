from phi_protect.domain.models import EntityType, Finding, FindingSource
from phi_protect.domain.policy.blocking import is_blocking

# When findings overlap, the label comes from (in order): a blocking finding over a non-blocking
# one; a specific label (MEMBER_ID) over the model's generic ID; a rule, which knows the field it
# matched, over a detector's guess; the higher score. Scores are only compared within that order,
# because rule and detector scores are not on the same scale.
GENERIC_ENTITIES = frozenset({EntityType.ID})


def merge_overlaps(findings: list[Finding], text: str) -> list[Finding]:
    """Joins overlapping findings, and same-type findings separated only by spaces.

    The merged span always covers every input span, so merging never shrinks a redaction. The label
    comes from the best member judged by its own score, so the result does not depend on the order
    detectors report in.
    """
    merged: list[Finding] = []
    for finding in sorted(findings, key=lambda f: f.start):
        if not merged or not _should_merge(merged[-1], finding, text):
            merged.append(finding)
            continue
        last = merged[-1]
        best = min(last, finding, key=_priority)
        merged[-1] = Finding(
            best.entity_type, last.start, max(last.end, finding.end), best.score, best.source
        )
    return merged


def _should_merge(last: Finding, finding: Finding, text: str) -> bool:
    if finding.start < last.end:
        return True
    gap = text[last.end : finding.start]
    return finding.entity_type == last.entity_type and not gap.strip(" ")


def _priority(finding: Finding) -> tuple:
    return (
        not is_blocking(finding),
        finding.entity_type in GENERIC_ENTITIES,
        finding.source != FindingSource.RULE,
        -finding.score,
        finding.entity_type.value,
    )
