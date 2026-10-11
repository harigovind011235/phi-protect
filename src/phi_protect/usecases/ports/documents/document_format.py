from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from phi_protect.domain.models import Finding


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    # Format-specific data the same adapter needs later to redact (e.g. character positions on PDF
    # pages). Opaque to the use case.
    layout: Any = None


class DocumentFormat(ABC):
    """Reads one file format into text and writes a redacted copy of it."""

    file_type: str
    media_type: str
    extension: str

    @abstractmethod
    def supports(self, data: bytes) -> bool:
        pass

    @abstractmethod
    async def extract(self, data: bytes) -> ExtractedDocument:
        """Raises UnverifiableFileError when the file cannot be fully checked."""
        pass

    @abstractmethod
    async def redact(
        self, data: bytes, document: ExtractedDocument, findings: list[Finding], labels: list[str]
    ) -> bytes:
        pass
