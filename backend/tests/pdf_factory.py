"""Small PDFs for tests, built with reportlab (no real documents)."""

from pathlib import Path

from reportlab.lib import pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

LINE = "Invoice No: INV-1042  Date: 2026-03-25  Total: 1,234.50 USD"
# A small invoice whose printed values match tests.test_pipeline.CONSISTENT.
INVOICE_LINES = [
    "Acme Ltd                                   INVOICE",
    "Invoice No: INV-1042      Date: 2026-03-25      Currency: USD",
    "Description        Qty    Unit price    Amount",
    "Widget             1      1,234.50      1,234.50",
    "Subtotal: 1,234.50",
    "Total: 1,234.50 USD",
]


def invoice_pdf(path: Path) -> Path:
    return text_pdf(path, lines=INVOICE_LINES)


def text_pdf(path: Path, pages: int = 1, lines: list[str] | None = None) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    for page in range(pages):
        y = 800
        for line in lines or [f"{LINE} page {page + 1}"] * 3:
            pdf.drawString(50, y, line)
            y -= 20
        pdf.showPage()
    pdf.save()
    return path


def image_only_pdf(path: Path) -> Path:
    """No text layer, like a scan: only drawn shapes."""
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.rect(50, 500, 400, 300, fill=1)
    pdf.showPage()
    pdf.save()
    return path


def encrypted_pdf(path: Path, user_password: str = "secret") -> Path:
    """``user_password=""`` gives a PDF that opens without a password but is
    still encrypted (owner password only)."""
    encrypt = pdfencrypt.StandardEncryption(user_password, ownerPassword="owner", strength=128)
    pdf = canvas.Canvas(str(path), pagesize=A4, encrypt=encrypt)
    for i in range(3):
        pdf.drawString(50, 800 - 20 * i, LINE)
    pdf.showPage()
    pdf.save()
    return path
