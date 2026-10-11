import pytest

from phi_protect.domain.models import EntityType, FindingSource
from phi_protect.domain.rules import find_rule_matches


def matches(text: str) -> set[tuple[EntityType, str]]:
    return {(f.entity_type, text[f.start : f.end]) for f in find_rule_matches(text)}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MRN: D0120", (EntityType.ACCOUNT_NUMBER, "D0120")),
        ("Claim number: D0120", (EntityType.CLAIM_NUMBER, "D0120")),
        ('{"memberId": "XGH884213901"}', (EntityType.MEMBER_ID, "XGH884213901")),
        ("Grp 00451122", (EntityType.GROUP_NUMBER, "00451122")),
        ("DOB: 03/14/1985", (EntityType.PATIENT_DATE, "03/14/1985")),
        ("date of service is March 1, 2026", (EntityType.PATIENT_DATE, "March 1, 2026")),
        ("DMG*D8*19850314*F~", (EntityType.PATIENT_DATE, "19850314")),
        ("Patient Le needs treatment.", (EntityType.PERSON, "Le")),
        ("Patient: Maria Lopez DOB: 03/14/1985", (EntityType.PERSON, "Maria Lopez")),
        ("MBI 1EG4-TE5-MK73", (EntityType.MEDICARE_ID, "1EG4-TE5-MK73")),
        ("Address: PO Box 1234", (EntityType.STREET_ADDRESS, "PO Box 1234")),
        ("Send to 123 main street, springfield", (EntityType.STREET_ADDRESS, "123 main street")),
        ("springfield, il 62704", (EntityType.LOCATION, "springfield, il 62704")),
        ("lives at 45 elm st, apt 3b", (EntityType.STREET_ADDRESS, "45 elm st, apt 3b")),
        ("Austin, TX 78701", (EntityType.ZIP_CODE, "78701")),
        ("N3*1420 W PECAN BLVD~", (EntityType.STREET_ADDRESS, "1420 W PECAN BLVD")),
        ("call 302-661-4014x193 today", (EntityType.PHONE_NUMBER, "302-661-4014x193")),
        ("NM1*IL*1*PATEL*ROHAN*K***MI*884213901~", (EntityType.PERSON, "PATEL")),
        ("NM1*IL*1*PATEL*ROHAN*K***MI*884213901~", (EntityType.PERSON, "ROHAN")),
        ("NM1*IL*1*PATEL*ROHAN*K***MI*884213901~", (EntityType.PERSON, "K")),
        ("NM1*QC*1*NG*KEVIN~", (EntityType.PERSON, "NG")),
        ("SSN: 000-12-3456", (EntityType.US_SSN, "000-12-3456")),
        ("social security number 123456789", (EntityType.US_SSN, "123456789")),
    ],
)
def test_rules_find_phi(text, expected):
    assert expected in matches(text)


@pytest.mark.parametrize(
    "text",
    [
        "copy 2 files to the shared drive",
        "processed in 12345 ms",
        "Patient Responsibility is $40 after insurance.",
        "Patient Portal login is broken",
        "patient = Patient(name=name)",
        "the patient count is 1500",
        "SELECT member_id, group_number, claim_status FROM claims",
        "Write a function that parses DOB fields in MM/DD/YYYY format",
        "NM1*82*1*ALVAREZ*MARIA****XX*1932104858~",
        "NM1*PR*2*DELTA DENTAL*****PI*94-0000000~",
    ],
)
def test_rules_ignore_look_alikes(text):
    assert matches(text) == set()


def test_rule_findings_are_marked_as_rules():
    assert {f.source for f in find_rule_matches("MRN: 12345678, PO Box 12")} == {FindingSource.RULE}


def test_x12_name_fields_are_separate_so_separators_survive():
    text = "NM1*IL*1*PATEL*ROHAN~"
    names = [text[f.start : f.end] for f in find_rule_matches(text) if f.entity_type == "PERSON"]
    assert names == ["PATEL", "ROHAN"]
