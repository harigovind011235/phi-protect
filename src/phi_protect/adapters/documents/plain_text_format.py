from phi_protect.domain.models import Finding
from phi_protect.domain.policy import replace_spans
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.ports.documents import DocumentFormat, ExtractedDocument

ENCODINGS = ("utf-8-sig", "cp1252")


class PlainTextFormat(DocumentFormat):
    """Any text file: CSV, JSON, logs, X12, code. Binary files (with NUL bytes) are not text."""

    file_type = "text"
    media_type = "text/plain; charset=utf-8"
    extension = "txt"

    def supports(self, data: bytes) -> bool:
        return b"\x00" not in data

    async def extract(self, data: bytes) -> ExtractedDocument:
        for encoding in ENCODINGS:
            try:
                return ExtractedDocument(text=data.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise UnverifiableFileError("text encoding not recognized")

    async def redact(
        self, data: bytes, document: ExtractedDocument, findings: list[Finding], labels: list[str]
    ) -> bytes:
        return replace_spans(document.text, findings, labels).encode()
