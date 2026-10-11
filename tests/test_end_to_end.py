"""Real container (NER model, rules, policy, file formats) wired as in production."""

import pytest
from fastapi.testclient import TestClient

from phi_protect.handler.app import create_app
from tests.pdf_factory import CLEAN_LINES, PHI_LINES, make_pdf

# Each pair: text, a value that must not survive de-identification.
MUST_BLOCK = [
    ("Patient SSN is 536-22-8754, please update the account.", "536-22-8754"),
    ('{"memberId": "XGH884213901"}', "XGH884213901"),
    ("Please write an appeal for patient Maria Lopez regarding her crown.", "Maria"),
    ("MRN: D0120", "D0120"),
    ("Claim number: D0120", "D0120"),
    ("Patient Dr. Smith has tooth pain.", "Smith"),
    ("NPI 1234567890; ID ZX987654321", "ZX987654321"),
    ("Send to 123 main street, springfield, il 62704.", "62704"),
    ("Address: PO Box 1234", "1234"),
    ("Patient Le needs treatment.", "Le "),
    ("DOB: 03/14/1985", "1985"),
    ("date of service 2026-03-01 for this claim", "2026-03-01"),
    ("DMG*D8*19850314*F~", "19850314"),
    ("lives at 45 elm st, apt 3b", "elm"),
    ("NM1*IL*1*PATEL*ROHAN****MI*884213901~", "PATEL"),
    ("Patient SSN: 000-12-3456", "000-12-3456"),
]

MUST_PASS = [
    "def get_patient(patient_id: int):\n    return db.get(patient_id)",
    "The release is scheduled for 03/14/2025.",
    "The NPI for the billing provider is 4507802119.",
    "Dr. Patel wants the frequency limitation for D2740 with Aetna.",
    "copy 2 files to the shared drive",
    "processed in 12345 ms",
    "Patient Responsibility is $40 after insurance.",
    "Our release on 2026-03-01 includes v2.1.0",
    "patient = Patient(name=name)",
    "Patient Portal login is broken",
    "SELECT member_id, dob FROM patients WHERE created_at > '2025-01-01'",
    "Write a function that parses DOB fields in MM/DD/YYYY format",
    "Ask Claude Code to review CLAUDE.md before merging",
    'ner_model_revision: str = "661b9c1c717d3165512d440abc3700c386aefab6"',
    "Add the hooks to /home/harigovindi/.claude/settings.json",
]


@pytest.mark.parametrize(("text", "sensitive"), MUST_BLOCK)
async def test_phi_is_blocked_and_removed(container, text, sensitive):
    result = await container.scan_service.scan_text(text)
    assert result.has_phi
    assert sensitive not in result.deidentified_text


@pytest.mark.parametrize("text", MUST_PASS)
async def test_look_alike_text_passes(container, text):
    assert not (await container.scan_service.scan_text(text)).has_phi


async def test_pdf_with_phi_is_blocked_and_clean_pdf_is_allowed(container):
    blocked = await container.file_service.scan_file(make_pdf(PHI_LINES))
    allowed = await container.file_service.scan_file(make_pdf(CLEAN_LINES))
    assert (blocked.decision, blocked.file_type) == ("block", "pdf")
    assert blocked.entity_counts["PERSON"] == 1
    assert allowed.decision == "allow"


async def test_csv_is_deidentified(container):
    data = b"name,dob,member_id\nMaria Lopez,03/14/1985,XGH884213901\n"
    result = await container.file_service.deidentify_file(data)
    assert result.media_type.startswith("text/plain")
    assert b"Maria" not in result.content and b"name,dob,member_id" in result.content


def test_http_wiring(container):
    client = TestClient(create_app(container))
    scanned = client.post("/scan", json={"text": "Call John Carter at (555) 201-8890"})
    assert scanned.json()["has_phi"]
    response = client.post("/scan-file", files={"file": ("eob.pdf", make_pdf(PHI_LINES))})
    assert response.json()["decision"] == "block"
