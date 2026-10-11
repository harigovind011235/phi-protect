import asyncio
import io
import threading

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image, ImageDraw, ImageFont

from phi_protect.domain.models import Finding
from phi_protect.usecases.errors import UnverifiableFileError
from phi_protect.usecases.ports.documents import DocumentFormat, ExtractedDocument

PDF_MAGIC = b"%PDF-"
MAX_IMAGE_PAGE_FRACTION = 0.1
RENDER_SCALE = 2
PAGE_SEPARATOR = "\n\n"
# Only human-written metadata is scanned; dates and producer fields hold machine values that look
# like IDs to the model.
SCANNED_METADATA_FIELDS = ("Title", "Author", "Subject", "Keywords")
MIN_LABEL_FONT_SIZE = 6

Rect = tuple[float, float, float, float]
# (page index, character index on that page) for every character of the extracted text, or None
# for characters that are not on a page (separators, metadata).
CharPositions = list[tuple[int, int] | None]


class PdfiumPdfFormat(DocumentFormat):
    """PDFs with a text layer, read with PDFium.

    The redacted copy is rebuilt from page images with labeled black boxes, so it has no text layer
    and redacted text cannot be recovered from it. PDFium is not thread-safe, so all PDFium work in
    this adapter runs in a worker thread under one lock.
    """

    file_type = "pdf"
    media_type = "application/pdf"
    extension = "pdf"

    def __init__(self, max_pages: int):
        self._max_pages = max_pages
        self._pdfium_lock = threading.Lock()

    def supports(self, data: bytes) -> bool:
        return data.startswith(PDF_MAGIC)

    async def extract(self, data: bytes) -> ExtractedDocument:
        return await asyncio.to_thread(self._locked, self._extract, data)

    async def redact(
        self, data: bytes, document: ExtractedDocument, findings: list[Finding], labels: list[str]
    ) -> bytes:
        return await asyncio.to_thread(
            self._locked, self._redact, data, document.layout, findings, labels
        )

    def _locked(self, function, *args):
        with self._pdfium_lock:
            return function(*args)

    def _extract(self, data: bytes) -> ExtractedDocument:
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as error:
            raise UnverifiableFileError("PDF is encrypted or damaged") from error
        if len(pdf) > self._max_pages:
            raise UnverifiableFileError(f"PDF has more than {self._max_pages} pages")
        if pdf.get_formtype() != pdfium_raw.FORMTYPE_NONE:
            raise UnverifiableFileError("PDF has fillable form fields; flatten or print it first")

        text_parts: list[str] = []
        positions: CharPositions = []
        for index, page in enumerate(pdf):
            page_text = _page_text(page, index)
            text_parts.append(page_text + PAGE_SEPARATOR)
            positions.extend((index, i) for i in range(len(page_text)))
            positions.extend([None] * len(PAGE_SEPARATOR))

        metadata = pdf.get_metadata_dict()
        metadata_text = " ".join(
            str(metadata[key]) for key in SCANNED_METADATA_FIELDS if metadata.get(key)
        )
        text_parts.append(metadata_text)
        positions.extend([None] * len(metadata_text))
        return ExtractedDocument(text="".join(text_parts), layout=positions)

    def _redact(
        self, data: bytes, positions: CharPositions, findings: list[Finding], labels: list[str]
    ) -> bytes:
        pdf = pdfium.PdfDocument(data)
        boxes_by_page = _boxes_by_page(pdf, positions, findings, labels)
        images = [_render_redacted(page, boxes_by_page.get(i, [])) for i, page in enumerate(pdf)]
        output = io.BytesIO()
        images[0].save(
            output, "PDF", save_all=True, append_images=images[1:], resolution=72 * RENDER_SCALE
        )
        return output.getvalue()


def _page_text(page: pdfium.PdfPage, index: int) -> str:
    reason = _unverifiable_page_reason(page)
    if reason:
        raise UnverifiableFileError(f"page {index + 1} {reason}")
    textpage = page.get_textpage()
    page_text = textpage.get_text_range()
    if len(page_text) != textpage.count_chars():
        raise UnverifiableFileError(f"page {index + 1} text could not be located")
    return page_text


def _unverifiable_page_reason(page: pdfium.PdfPage) -> str | None:
    if _has_non_link_annotations(page):
        return "has comments or annotations"
    page_area = page.get_width() * page.get_height()
    for image in page.get_objects(filter=[pdfium_raw.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = image.get_bounds()
        if (right - left) * (top - bottom) > MAX_IMAGE_PAGE_FRACTION * page_area:
            return (
                "contains an image, which cannot be checked for PHI "
                "(scanned page, x-ray or screenshot)"
            )
    return None


def _has_non_link_annotations(page: pdfium.PdfPage) -> bool:
    for i in range(pdfium_raw.FPDFPage_GetAnnotCount(page.raw)):
        annotation = pdfium_raw.FPDFPage_GetAnnot(page.raw, i)
        subtype = pdfium_raw.FPDFAnnot_GetSubtype(annotation)
        pdfium_raw.FPDFPage_CloseAnnot(annotation)
        if subtype != pdfium_raw.FPDF_ANNOT_LINK:
            return True
    return False


def _boxes_by_page(
    pdf: pdfium.PdfDocument, positions: CharPositions, findings: list[Finding], labels: list[str]
) -> dict[int, list[tuple[Rect, str]]]:
    textpages: dict[int, pdfium.PdfTextPage] = {}
    boxes: dict[int, list[tuple[Rect, str]]] = {}
    for finding, label in zip(findings, labels, strict=True):
        finding_positions = positions[finding.start : finding.end]
        for page_index, rect in _line_rects(pdf, textpages, finding_positions):
            boxes.setdefault(page_index, []).append((rect, label))
    return boxes


def _line_rects(
    pdf: pdfium.PdfDocument, textpages: dict, positions: CharPositions
) -> list[tuple[int, Rect]]:
    """Merges one finding's character boxes into one rectangle per page and line (PDF points)."""
    rects: list[tuple[int, Rect]] = []
    for position in positions:
        if position is None:
            continue
        page_index, char_index = position
        if page_index not in textpages:
            textpages[page_index] = pdf[page_index].get_textpage()
        left, bottom, right, top = textpages[page_index].get_charbox(char_index)
        if right <= left and top <= bottom:
            continue
        if not rects or not _same_line(rects[-1], page_index, bottom, top):
            rects.append((page_index, (left, bottom, right, top)))
            continue
        _, (last_left, last_bottom, last_right, last_top) = rects[-1]
        rects[-1] = (
            page_index,
            (
                min(last_left, left),
                min(last_bottom, bottom),
                max(last_right, right),
                max(last_top, top),
            ),
        )
    return rects


def _same_line(previous: tuple[int, Rect], page_index: int, bottom: float, top: float) -> bool:
    previous_page, (_, previous_bottom, _, previous_top) = previous
    return previous_page == page_index and bottom <= previous_top and top >= previous_bottom


def _render_redacted(page: pdfium.PdfPage, boxes: list[tuple[Rect, str]]) -> Image.Image:
    rotation = page.get_rotation()
    page.set_rotation(0)
    bitmap = page.render(scale=RENDER_SCALE, draw_annots=False, may_draw_forms=False)
    image = bitmap.to_pil().convert("RGB")
    # The visible page area (crop box within media box), which is what gets rendered.
    crop_left, _, _, crop_top = page.get_bbox()
    draw = ImageDraw.Draw(image)
    for (left, bottom, right, top), label in boxes:
        x0, y0 = (left - crop_left) * RENDER_SCALE - 2, (crop_top - top) * RENDER_SCALE - 2
        x1, y1 = (right - crop_left) * RENDER_SCALE + 2, (crop_top - bottom) * RENDER_SCALE + 2
        draw.rectangle((x0, y0, x1, y1), fill="black")
        _draw_label(draw, (x0, y0, x1, y1), label)
    return image.rotate(-rotation, expand=True) if rotation else image


def _draw_label(draw: ImageDraw.ImageDraw, box: Rect, label: str) -> None:
    """Writes the placeholder inside the box, shrinking it to fit; tiny boxes stay plain black."""
    x0, y0, x1, y1 = box
    size = int((y1 - y0) * 0.7)
    while size >= MIN_LABEL_FONT_SIZE:
        font = ImageFont.load_default(size=size)
        if draw.textlength(label, font=font) <= x1 - x0 - 4:
            draw.text((x0 + 2, y0 + 1), label, fill="white", font=font)
            return
        size -= 1
