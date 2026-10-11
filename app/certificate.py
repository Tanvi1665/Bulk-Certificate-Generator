"""Builds ONE certificate PDF from the single predefined template.

The template is simply this function's layout: border, title, name, course, date.
"""
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)  # about 842 x 595 points
NAVY = HexColor("#1F3A5F")
GOLD = HexColor("#B8860B")
GREY = HexColor("#555555")


def _fit_font_size(text: str, font: str, max_size: int, max_width: float, min_size: int = 12) -> int:
    """Shrink the font until the text fits the page, so long names never overflow."""
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def generate_certificate_pdf(
    output_path: Path,
    *,
    recipient_name: str,
    course_name: str,
    organization: str,
    issue_date: date,
    certificate_id: str,
) -> None:
    max_text_width = PAGE_W - 160
    cx = PAGE_W / 2

    # pageCompression=0 keeps the PDF text readable as plain bytes, which lets
    # the tests check that the recipient's name is really inside the file.
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H), pageCompression=0)
    c.setTitle(f"Certificate - {recipient_name}")
    c.setAuthor(organization)

    # Double border
    c.setStrokeColor(NAVY)
    c.setLineWidth(4)
    c.rect(25, 25, PAGE_W - 50, PAGE_H - 50)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.rect(38, 38, PAGE_W - 76, PAGE_H - 76)

    # Header
    c.setFillColor(GREY)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(cx, PAGE_H - 95, organization.upper())

    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 40)
    c.drawCentredString(cx, PAGE_H - 150, "CERTIFICATE OF COMPLETION")
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.line(cx - 150, PAGE_H - 170, cx + 150, PAGE_H - 170)

    # Recipient-specific content
    c.setFillColor(GREY)
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, PAGE_H - 215, "This is to certify that")

    name_font = "Times-BoldItalic"
    name_size = _fit_font_size(recipient_name, name_font, 42, max_text_width)
    c.setFillColor(NAVY)
    c.setFont(name_font, name_size)
    c.drawCentredString(cx, PAGE_H - 280, recipient_name)
    c.setStrokeColor(GREY)
    c.setLineWidth(0.5)
    c.line(cx - 200, PAGE_H - 292, cx + 200, PAGE_H - 292)

    c.setFillColor(GREY)
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, PAGE_H - 335, "has successfully completed")

    course_font = "Helvetica-Bold"
    course_size = _fit_font_size(course_name, course_font, 26, max_text_width)
    c.setFillColor(NAVY)
    c.setFont(course_font, course_size)
    c.drawCentredString(cx, PAGE_H - 385, course_name)

    # Footer: date on the left, unique certificate ID on the right
    c.setFillColor(GREY)
    c.setFont("Helvetica", 11)
    c.drawString(90, 95, f"Date of issue: {issue_date.strftime('%d %B %Y')}")
    c.setFont("Helvetica", 9)
    c.drawRightString(PAGE_W - 90, 95, f"Certificate ID: {certificate_id}")

    c.showPage()
    c.save()
