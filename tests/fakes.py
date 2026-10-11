import re

from phi_protect.domain.models import EntityType, Finding
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.ports.detectors import PhiDetector
from phi_protect.usecases.ports.documents import DocumentFormat, ExtractedDocument


class FakeDetector(PhiDetector):
    """Returns the given (value, type) pairs wherever the value occurs in the text."""

    def __init__(self, values: list[tuple[str, EntityType]] | None = None):
        self._values = values or []
        self.calls: list[str] = []

    async def detect(self, text: str) -> list[Finding]:
        self.calls.append(text)
        return [
            Finding(entity_type, match.start(), match.end(), 0.9)
            for value, entity_type in self._values
            for match in re.finditer(re.escape(value), text)
        ]


class FakeFormat(DocumentFormat):
    file_type = "fake"
    media_type = "application/x-fake"
    extension = "fake"

    def __init__(self, prefix: bytes = b"FAKE", unverifiable_reason: str | None = None):
        self._prefix = prefix
        self._unverifiable_reason = unverifiable_reason
        self.redactions: list[tuple[list[Finding], list[str]]] = []

    def supports(self, data: bytes) -> bool:
        return data.startswith(self._prefix)

    async def extract(self, data: bytes) -> ExtractedDocument:
        if self._unverifiable_reason:
            raise UnverifiableFileError(self._unverifiable_reason)
        return ExtractedDocument(text=data[len(self._prefix) :].decode())

    async def redact(
        self, data: bytes, document: ExtractedDocument, findings: list[Finding], labels: list[str]
    ) -> bytes:
        self.redactions.append((findings, labels))
        return b"redacted"
