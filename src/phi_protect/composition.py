"""
Composition root: the only place adapters are instantiated and wired to ports.
"""

from dataclasses import dataclass

from phi_protect.adapters.detectors.presidio_phi_detector import PresidioPhiDetector
from phi_protect.adapters.documents.pdfium_pdf_format import PdfiumPdfFormat
from phi_protect.adapters.documents.plain_text_format import PlainTextFormat
from phi_protect.config.settings import Settings
from phi_protect.usecases.file_service import FileService
from phi_protect.usecases.interfaces import FileServiceInterface, ScanServiceInterface
from phi_protect.usecases.ports.detectors import PhiDetector
from phi_protect.usecases.ports.documents import DocumentFormat
from phi_protect.usecases.scan_service import ScanService


@dataclass(frozen=True)
class Container:
    """Holds all adapter and service instances for the app lifetime."""

    settings: Settings
    phi_detector: PhiDetector
    scan_service: ScanServiceInterface
    file_service: FileServiceInterface


def create_container(settings: Settings) -> Container:
    phi_detector = PresidioPhiDetector(
        model_name=settings.ner_model,
        model_revision=settings.ner_model_revision,
        score_threshold=settings.score_threshold,
        max_concurrent_scans=settings.max_concurrent_scans,
    )
    # The first format that supports the data wins, so PDF must come before plain text.
    document_formats: list[DocumentFormat] = [
        PdfiumPdfFormat(max_pages=settings.max_pdf_pages),
        PlainTextFormat(),
    ]

    scan_service = ScanService(detector=phi_detector)
    file_service = FileService(
        detector=phi_detector,
        formats=document_formats,
        max_file_bytes=settings.max_file_bytes,
        max_text_chars=settings.max_file_text_chars,
    )

    return Container(
        settings=settings,
        phi_detector=phi_detector,
        scan_service=scan_service,
        file_service=file_service,
    )
