from itertools import permutations

import pytest

from phi_protect.domain.models import Decision, EntityType, Finding, FindingSource
from phi_protect.domain.policy import (
    decide,
    deidentify,
    is_allowed,
    merge_overlaps,
    resolve_findings,
)

RULE = FindingSource.RULE


def test_same_value_gets_same_placeholder():
    text = "Ann met Bob, then Ann left"
    findings = [
        Finding(EntityType.PERSON, 0, 3, 0.9),
        Finding(EntityType.PERSON, 8, 11, 0.9),
        Finding(EntityType.PERSON, 18, 21, 0.9),
    ]
    assert deidentify(text, findings) == "[PERSON_1] met [PERSON_2], then [PERSON_1] left"


def test_overlap_prefers_specific_label_and_covers_widest_span():
    findings = [Finding(EntityType.ID, 10, 20, 0.99), Finding(EntityType.MEMBER_ID, 8, 20, 0.85)]
    assert merge_overlaps(findings, "x" * 30) == [Finding(EntityType.MEMBER_ID, 8, 20, 0.85)]


def test_adjacent_name_parts_are_joined():
    text = "Maria Lopez, Ann"
    findings = [
        Finding(EntityType.PERSON, 0, 5, 0.7),
        Finding(EntityType.PERSON, 6, 11, 0.5),
        Finding(EntityType.PERSON, 13, 16, 0.9),
    ]
    assert deidentify(text, merge_overlaps(findings, text)) == "[PERSON_1], [PERSON_2]"


@pytest.mark.parametrize("order", [1, -1])
def test_overlap_keeps_blocking_label_over_higher_scoring_non_blocking(order):
    findings = [
        Finding(EntityType.MEMBER_ID, 0, 10, 0.85),
        Finding(EntityType.DATE_TIME, 0, 10, 0.99),
    ]
    assert merge_overlaps(findings[::order], "x" * 10)[0].entity_type == EntityType.MEMBER_ID


def test_merged_label_does_not_depend_on_detector_order():
    cluster = [
        Finding(EntityType.DATE_TIME, 0, 10, 1.0),
        Finding(EntityType.PATIENT_DATE, 0, 10, 0.85, RULE),
        Finding(EntityType.PHONE_NUMBER, 0, 10, 0.75),
    ]
    labels = {
        merge_overlaps(list(order), "x" * 10)[0].entity_type for order in permutations(cluster)
    }
    assert labels == {EntityType.PATIENT_DATE}


def test_rule_label_beats_higher_scoring_detector_label():
    findings = [
        Finding(EntityType.PERSON, 3, 9, 0.95),
        Finding(EntityType.STREET_ADDRESS, 0, 20, 0.85, RULE),
    ]
    assert merge_overlaps(findings, "x" * 20)[0].entity_type == EntityType.STREET_ADDRESS


@pytest.mark.parametrize(
    ("text", "value", "entity_type", "allowed"),
    [
        ("Dr. Patel did the crown", "Dr. Patel", EntityType.PERSON, True),
        ("Patient Dr. Smith has pain", "Smith", EntityType.PERSON, False),
        ("MRN: D0120", "D0120", EntityType.ACCOUNT_NUMBER, False),
        ("MRN: D0120", "D0120", EntityType.ID, True),
        ("The NPI is 4507802119", "4507802119", EntityType.ID, True),
        ("NPI 1234567890; ID ZX987654321", "ZX987654321", EntityType.ID, False),
        ("PR #3429 is ready", "3429", EntityType.PHONE_NUMBER, True),
        ("Billed to Delta Dental", "Delta Dental", EntityType.PERSON, True),
        ("Maria Lopez called", "Maria Lopez", EntityType.PERSON, False),
        ("Ask Claude to review", "Claude", EntityType.PERSON, True),
        ("Read CLAUDE.md first", "CLAUDE.md", EntityType.PERSON, True),
        ("Claude Dubois called", "Claude Dubois", EntityType.PERSON, False),
        (
            "rev 661b9c1c717d3165512d440abc3700c386aefab6",
            "661b9c1c717d3165512d440abc3700c386aefab6",
            EntityType.ID,
            True,
        ),
        (
            "id 123e4567-e89b-12d3-a456-426614174000",
            "123e4567-e89b-12d3-a456-426614174000",
            EntityType.ID,
            True,
        ),
        ("Member W884213901", "W884213901", EntityType.ID, False),
        ("open /home/harigovindi/.claude/settings.json", "harigovindi", EntityType.PERSON, True),
        ("C:\\Users\\harigovindi\\.claude", "harigovindi", EntityType.PERSON, True),
        ("cd /Users/jdoe42/projects", "jdoe42", EntityType.ID, True),
        ("see ~/.claude/settings.json", ".claude", EntityType.PERSON, True),
        ("the home of Maria Lopez", "Maria Lopez", EntityType.PERSON, False),
    ],
)
def test_allowlist(text, value, entity_type, allowed):
    start = text.index(value)
    assert is_allowed(text, entity_type, start, start + len(value)) is allowed


def test_allowlist_runs_before_merge_so_it_cannot_erase_another_finding():
    text = "Austin, TX 97329"
    start = text.index("97329")
    candidates = [
        Finding(EntityType.PHONE_NUMBER, start, start + 5, 0.99),
        Finding(EntityType.ZIP_CODE, start, start + 5, 0.6, RULE),
    ]
    assert [f.entity_type for f in resolve_findings(text, candidates)] == [EntityType.ZIP_CODE]


def test_allowlist_never_overrules_rule_findings():
    text = "NM1*IL*1*CO*JANE~"
    start = text.index("CO")
    rule_finding = Finding(EntityType.PERSON, start, start + 2, 0.85, RULE)
    detector_finding = Finding(EntityType.PERSON, start, start + 2, 0.9)
    assert resolve_findings(text, [rule_finding]) == [rule_finding]
    assert resolve_findings(text, [detector_finding]) == []


def test_unlabeled_dates_do_not_block_but_patient_dates_do():
    assert decide([Finding(EntityType.DATE_TIME, 0, 10, 1.0)]) == Decision.ALLOW
    assert decide([Finding(EntityType.PATIENT_DATE, 0, 10, 0.85, RULE)]) == Decision.BLOCK
    assert decide([]) == Decision.ALLOW
