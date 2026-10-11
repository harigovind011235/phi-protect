from phi_protect.domain.models import Decision, EntityType, Finding

# An unlabeled date identifies no one, so it gets replaced but never causes a block.
# Labeled dates (DOB, date of service) are PATIENT_DATE and do block.
NON_BLOCKING_ENTITIES = frozenset({EntityType.DATE_TIME})


def is_blocking(finding: Finding) -> bool:
    return finding.entity_type not in NON_BLOCKING_ENTITIES


def decide(findings: list[Finding]) -> Decision:
    return Decision.BLOCK if any(is_blocking(f) for f in findings) else Decision.ALLOW
