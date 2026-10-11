import io

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PHI_LINES = ["Patient: Maria Lopez   DOB: 03/14/1985", "Call the member at (512) 555-0142"]
CLEAN_LINES = [
    "Guardian frequency limitation for D2740 is once every 5 years.",
    "Dr. Alvarez, NPI 1932104858",
]


def make_pdf(lines: list[str], decorate=None, pages: int = 1, rotate: int = 0, **options) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, **options)
    for _ in range(pages):
        if rotate:
            pdf.setPageRotation(rotate)
        pdf.setFont("Helvetica", 11)
        for i, line in enumerate(lines):
            pdf.drawString(72, 500 - 22 * i, line)
        if decorate:
            decorate(pdf)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def image_only_pdf() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (612, 792), "white").save(buffer, "PDF")
    return buffer.getvalue()


def dark_fraction(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    histogram = image.crop(box).convert("L").histogram()
    return sum(histogram[:80]) / sum(histogram)
