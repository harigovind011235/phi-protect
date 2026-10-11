import pytest

from phi_protect.domain.models import EntityType
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.file_service import FileService
from tests.fakes import FakeDetector, FakeFormat


def make_service(*formats: FakeFormat, max_file_bytes: int = 1000, max_text_chars: int = 1000):
    detector = FakeDetector([("Maria Lopez", EntityType.PERSON)])
    return FileService(detector, list(formats), max_file_bytes, max_text_chars)


async def test_file_with_phi_is_blocked_with_counts():
    result = await make_service(FakeFormat()).scan_file(b"FAKEMaria Lopez, MRN: 12345678")
    assert result.decision == "block"
    assert result.file_type == "fake"
    assert result.entity_counts == {"PERSON": 1, "ACCOUNT_NUMBER": 1}


async def test_clean_file_is_allowed():
    result = await make_service(FakeFormat()).scan_file(b"FAKEfrequency limits for D2740")
    assert result.decision == "allow"


@pytest.mark.parametrize(
    ("service", "data", "reason"),
    [
        (make_service(FakeFormat(), max_file_bytes=5), b"FAKE too big", "larger than 5 bytes"),
        (make_service(FakeFormat()), b"OTHER", "unsupported binary file type"),
        (make_service(FakeFormat(unverifiable_reason="scanned page")), b"FAKEx", "scanned page"),
        (make_service(FakeFormat(), max_text_chars=3), b"FAKEtoo long", "more than 3 characters"),
    ],
)
async def test_files_that_cannot_be_checked(service, data, reason):
    result = await service.scan_file(data)
    assert result.decision == "cannot_verify"
    assert reason in result.reason
    with pytest.raises(UnverifiableFileError, match=reason):
        await service.deidentify_file(data)


async def test_unsupported_file_type_is_unknown():
    result = await make_service(FakeFormat()).scan_file(b"OTHER")
    assert result.file_type == "unknown"


async def test_first_supporting_format_wins():
    first, second = FakeFormat(prefix=b"FA"), FakeFormat(prefix=b"FAKE")
    await make_service(first, second).deidentify_file(b"FAKEMaria Lopez")
    assert len(first.redactions) == 1
    assert second.redactions == []


async def test_deidentify_passes_placeholders_to_the_format():
    file_format = FakeFormat()
    result = await make_service(file_format).deidentify_file(b"FAKEMaria Lopez and Maria Lopez")
    assert result.content == b"redacted"
    assert (result.media_type, result.extension) == ("application/x-fake", "fake")
    _, labels = file_format.redactions[0]
    assert labels == ["[PERSON_1]", "[PERSON_1]"]
