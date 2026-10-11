import pytest
from fastapi.testclient import TestClient

from phi_protect.composition import Container
from phi_protect.config.settings import Settings
from phi_protect.handler.app import create_app
from phi_protect.usecases.dtos import DeidentifiedFile, FileScanResult, ScanResult
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.interfaces import FileServiceInterface, ScanServiceInterface
from tests.fakes import FakeDetector


class StubScanService(ScanServiceInterface):
    async def scan_text(self, text: str) -> ScanResult:
        return ScanResult(has_phi=True, deidentified_text="[PERSON_1]")


class StubFileService(FileServiceInterface):
    def __init__(self):
        self.received: list[bytes] = []

    async def scan_file(self, data: bytes) -> FileScanResult:
        self.received.append(data)
        return FileScanResult("block", "pdf", entity_counts={"PERSON": 1})

    async def deidentify_file(self, data: bytes) -> DeidentifiedFile:
        if data == b"bad":
            raise UnverifiableFileError("page 1 contains an image")
        return DeidentifiedFile(b"%PDF-redacted", "application/pdf", "pdf")


@pytest.fixture
def file_service() -> StubFileService:
    return StubFileService()


@pytest.fixture
def client(file_service) -> TestClient:
    container = Container(
        settings=Settings(max_file_bytes=10),
        phi_detector=FakeDetector(),
        scan_service=StubScanService(),
        file_service=file_service,
    )
    return TestClient(create_app(container))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_scan_returns_service_result(client):
    body = client.post("/scan", json={"text": "Maria Lopez"}).json()
    assert body == {"has_phi": True, "entities": [], "deidentified_text": "[PERSON_1]"}


@pytest.mark.parametrize(
    "payload", [{"text": ["SECRET-MARKER"]}, {"text": "SECRET-MARKER " * 20_000}, {"other": 1}]
)
def test_validation_errors_do_not_echo_input(client, payload):
    response = client.post("/scan", json=payload)
    assert response.status_code == 422
    assert "SECRET-MARKER" not in response.text


def test_upload_is_read_only_up_to_one_byte_over_the_limit(client, file_service):
    client.post("/scan-file", files={"file": ("a.pdf", b"x" * 100)})
    assert len(file_service.received[0]) == 11


def test_deidentified_file_never_reuses_the_original_name(client):
    response = client.post("/deidentify-file", files={"file": ("Maria_Lopez_EOB.pdf", b"%PDF")})
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="deidentified.pdf"'


def test_unverifiable_file_is_rejected_with_reason(client):
    response = client.post("/deidentify-file", files={"file": ("scan.pdf", b"bad")})
    assert response.status_code == 422
    assert response.json() == {"decision": "cannot_verify", "reason": "page 1 contains an image"}
