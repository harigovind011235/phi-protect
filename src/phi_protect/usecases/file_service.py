from collections import Counter

from phi_protect.domain.models import Decision, Finding
from phi_protect.domain.policy import decide, placeholders
from phi_protect.usecases.dtos import DeidentifiedFile, FileScanResult
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.interfaces import FileServiceInterface
from phi_protect.usecases.phi_search import find_phi
from phi_protect.usecases.ports.detectors import PhiDetector
from phi_protect.usecases.ports.documents import DocumentFormat, ExtractedDocument

UNKNOWN_FILE_TYPE = "unknown"


class FileService(FileServiceInterface):
    def __init__(
        self,
        detector: PhiDetector,
        formats: list[DocumentFormat],
        max_file_bytes: int,
        max_text_chars: int,
    ):
        self._detector = detector
        self._formats = formats
        self._max_file_bytes = max_file_bytes
        self._max_text_chars = max_text_chars

    async def scan_file(self, data: bytes) -> FileScanResult:
        file_format = self._format_for(data)
        file_type = file_format.file_type if file_format else UNKNOWN_FILE_TYPE
        try:
            _, _, findings = await self._analyze(data)
        except UnverifiableFileError as error:
            return FileScanResult(Decision.CANNOT_VERIFY.value, file_type, reason=str(error))
        counts = Counter(f.entity_type.value for f in findings)
        return FileScanResult(decide(findings).value, file_type, entity_counts=dict(counts))

    async def deidentify_file(self, data: bytes) -> DeidentifiedFile:
        file_format, document, findings = await self._analyze(data)
        labels = placeholders(document.text, findings)
        content = await file_format.redact(data, document, findings, labels)
        return DeidentifiedFile(content, file_format.media_type, file_format.extension)

    def _format_for(self, data: bytes) -> DocumentFormat | None:
        return next((f for f in self._formats if f.supports(data)), None)

    async def _analyze(
        self, data: bytes
    ) -> tuple[DocumentFormat, ExtractedDocument, list[Finding]]:
        if len(data) > self._max_file_bytes:
            raise UnverifiableFileError(f"file is larger than {self._max_file_bytes} bytes")
        file_format = self._format_for(data)
        if file_format is None:
            raise UnverifiableFileError("unsupported binary file type")
        document = await file_format.extract(data)
        if len(document.text) > self._max_text_chars:
            raise UnverifiableFileError(
                f"file has more than {self._max_text_chars} characters of text"
            )
        return file_format, document, await find_phi(self._detector, document.text)
