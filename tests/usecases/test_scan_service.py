from phi_protect.domain.models import EntityType
from phi_protect.usecases.scan_service import ScanService
from tests.fakes import FakeDetector


async def test_detector_findings_and_rules_are_combined():
    service = ScanService(FakeDetector([("Maria Lopez", EntityType.PERSON)]))
    result = await service.scan_text("Patient Maria Lopez, MRN: 12345678")
    assert result.has_phi
    assert result.deidentified_text == "Patient [PERSON_1], MRN: [ACCOUNT_NUMBER_1]"
    assert [e.entity_type for e in result.entities] == ["PERSON", "ACCOUNT_NUMBER"]


async def test_allowlisted_detector_findings_are_dropped():
    service = ScanService(FakeDetector([("Dr. Patel", EntityType.PERSON)]))
    result = await service.scan_text("Dr. Patel asked about D2740")
    assert not result.has_phi
    assert result.entities == []


async def test_unlabeled_date_is_replaced_but_does_not_block():
    service = ScanService(FakeDetector([("03/14/2025", EntityType.DATE_TIME)]))
    result = await service.scan_text("Release on 03/14/2025")
    assert not result.has_phi
    assert result.deidentified_text == "Release on [DATE_TIME_1]"


async def test_blank_text_skips_detection():
    detector = FakeDetector()
    result = await ScanService(detector).scan_text("   ")
    assert not result.has_phi
    assert result.deidentified_text == "   "
    assert detector.calls == []
