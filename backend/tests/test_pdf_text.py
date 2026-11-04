import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.pdf_text import PdfRejected, check_upload, extract_text, sanitize_filename
from tests.pdf_factory import encrypted_pdf, image_only_pdf, text_pdf

MB = 2**20


def _code(callable_, *args, **kwargs):
    with pytest.raises(PdfRejected) as info:
        callable_(*args, **kwargs)
    return info.value.code


def test_text_pdf_extracts_every_page_with_markers(tmp_path):
    result = extract_text(text_pdf(tmp_path / "a.pdf", pages=2), max_pages=20)
    assert result.page_count == 2
    assert "INV-1042" in result.pages[0]
    assert result.text.index("[pdf page 1 of 2]") < result.text.index("[pdf page 2 of 2]")


def test_reading_order_is_top_to_bottom_not_drawing_order(tmp_path):
    path = tmp_path / "order.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    pdf.drawString(50, 300, "Bottom line drawn first, with enough text for a text layer.")
    pdf.drawString(50, 800, "Top line drawn second, with enough text for a text layer.")
    pdf.showPage()
    pdf.save()
    text = extract_text(path, max_pages=20).text
    assert text.index("Top line") < text.index("Bottom line")


def test_image_only_pdf_is_rejected_as_scanned(tmp_path):
    assert _code(extract_text, image_only_pdf(tmp_path / "scan.pdf"), 20) == (
        "SCANNED_PDF_UNSUPPORTED"
    )


@pytest.mark.parametrize("user_password", ["secret", ""])
def test_encrypted_pdf_is_rejected(tmp_path, user_password):
    path = encrypted_pdf(tmp_path / "locked.pdf", user_password)
    assert _code(extract_text, path, 20) == "ENCRYPTED_PDF"


def test_page_limit(tmp_path):
    path = text_pdf(tmp_path / "long.pdf", pages=3)
    assert _code(extract_text, path, 2) == "TOO_MANY_PAGES"
    assert extract_text(path, max_pages=3).page_count == 3


def test_corrupt_pdf_is_rejected(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nthis is not really a pdf\n")
    assert _code(extract_text, path, 20) == "INVALID_PDF"


@pytest.mark.parametrize(
    ("filename", "content_type", "head", "size", "code"),
    [
        ("a.pdf", "application/pdf", b"%PDF-1.7", 11 * MB, "FILE_TOO_LARGE"),
        ("a.pdf", "application/pdf", b"", 0, "NOT_A_PDF"),
        ("a.exe", "application/pdf", b"%PDF-1.7", 100, "NOT_A_PDF"),
        ("a.pdf", "text/html", b"%PDF-1.7", 100, "NOT_A_PDF"),
        ("a.pdf", "application/pdf", b"MZ\x90\x00", 100, "NOT_A_PDF"),
        (None, "application/pdf", b"%PDF-1.7", 100, "NOT_A_PDF"),
    ],
)
def test_upload_checks_reject(filename, content_type, head, size, code):
    assert _code(check_upload, filename, content_type, head, size, 10 * MB) == code


def test_upload_checks_accept_a_pdf():
    check_upload("Invoice.PDF", "application/pdf; charset=binary", b"%PDF-1.7\n", 100, 10 * MB)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\x\\invoice<1>.pdf", "invoice_1_.pdf"),
        ("  .hidden.pdf  ", "hidden.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("a" * 300 + ".pdf", "a" * 120),
    ],
)
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected
