import asyncio

import pypdfium2 as pdfium
import pytest

from phi_protect.adapters.documents.pdfium_pdf_format import PdfiumPdfFormat
from phi_protect.domain.models import EntityType, Finding
from phi_protect.usecases.errors import UnverifiableFileError
from tests.pdf_factory import PHI_LINES, dark_fraction, image_only_pdf, make_pdf

pdf_format = PdfiumPdfFormat(max_pages=5)


def finding(text: str, value: str) -> Finding:
    start = text.index(value)
    return Finding(EntityType.PERSON, start, start + len(value), 0.9)


async def test_extracts_page_text_and_only_human_metadata():
    data = make_pdf(PHI_LINES, decorate=lambda c: c.setTitle("Maria Lopez EOB"))
    document = await pdf_format.extract(data)
    assert "Patient: Maria Lopez" in document.text
    assert "Maria Lopez EOB" in document.text
    assert "D:20" not in document.text
    assert len(document.layout) == len(document.text)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (image_only_pdf(), "image"),
        (
            make_pdf(PHI_LINES, decorate=lambda c: c.acroForm.textfield(name="n", x=72, y=300)),
            "form",
        ),
        (
            make_pdf(PHI_LINES, decorate=lambda c: c.textAnnotation("x", Rect=(72, 300, 200, 350))),
            "annotation",
        ),
        (make_pdf(PHI_LINES, encrypt="secret"), "encrypted"),
        (make_pdf(PHI_LINES, pages=6), "more than 5 pages"),
    ],
)
async def test_pdfs_that_cannot_be_checked(data, reason):
    with pytest.raises(UnverifiableFileError, match=reason):
        await pdf_format.extract(data)


async def test_redacted_pdf_has_no_text_and_boxes_cover_findings():
    original = make_pdf(PHI_LINES)
    document = await pdf_format.extract(original)
    findings = [finding(document.text, "Maria Lopez"), finding(document.text, "(512) 555-0142")]
    output = await pdf_format.redact(original, document, findings, ["[PERSON_1]", "[PHONE_1]"])

    redacted_page = pdfium.PdfDocument(output)[0]
    assert redacted_page.get_textpage().get_text_range() == ""
    image = redacted_page.render(scale=1).to_pil()
    source_page = pdfium.PdfDocument(original)[0]
    textpage, height = source_page.get_textpage(), source_page.get_height()
    page_text = textpage.get_text_range()
    for value, covered in (("Maria Lopez", True), ("555-0142", True), ("Patient", False)):
        start = page_text.index(value)
        left, bottom, _, top = textpage.get_charbox(start)
        right = textpage.get_charbox(start + len(value) - 1)[2]
        assert (dark_fraction(image, (left, height - top, right, height - bottom)) > 0.5) is covered


async def test_rotated_pages_keep_their_orientation():
    original = make_pdf(PHI_LINES, rotate=90)
    document = await pdf_format.extract(original)
    output = await pdf_format.redact(
        original, document, [finding(document.text, "Maria Lopez")], ["[P]"]
    )
    expected_size = pdfium.PdfDocument(original)[0].render(scale=1).to_pil().size
    assert pdfium.PdfDocument(output)[0].render(scale=1).to_pil().size == expected_size


async def test_parallel_requests_are_safe():
    data = make_pdf(PHI_LINES)
    documents = await asyncio.gather(*(pdf_format.extract(data) for _ in range(8)))
    assert len({d.text for d in documents}) == 1
