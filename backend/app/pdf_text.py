"""Upload checks and text extraction for text-based PDFs.

The text is untrusted input: it is only ever passed to the LLM as labeled data
(see ``app.prompt``), never interpreted.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePath

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

PDF_MAGIC = b"%PDF-"
ALLOWED_CONTENT_TYPES = {"application/pdf"}
# Fewer visible characters than this per page means there is no real text
# layer (a scan or an image-only PDF). Our smallest synthetic invoice has ~600.
MIN_CHARS_PER_PAGE = 50
MAX_DISPLAY_NAME = 120


class PdfRejected(Exception):
    """The file cannot be processed. ``code`` matches the API error codes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PdfText:
    pages: list[str]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        """All pages, in order, with a page marker before each page."""
        total = len(self.pages)
        return "\n\n".join(
            f"[pdf page {number} of {total}]\n{page}" for number, page in enumerate(self.pages, 1)
        )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: str | None) -> str:
    """Display-only name: never used as a path on disk."""
    base = PurePath((name or "").replace("\\", "/")).name
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^\w.\- ()]", "_", base).strip(" .")
    base = re.sub(r"_+", "_", base)
    return base[:MAX_DISPLAY_NAME] or "document.pdf"


def check_upload(
    filename: str | None, content_type: str | None, head: bytes, size: int, max_bytes: int
) -> None:
    """Extension, declared type and magic bytes must agree; size within the limit."""
    if size > max_bytes:
        raise PdfRejected("FILE_TOO_LARGE", f"File is larger than {max_bytes // 2**20} MB.")
    if size == 0:
        raise PdfRejected("NOT_A_PDF", "File is empty.")
    if not (filename or "").lower().endswith(".pdf"):
        raise PdfRejected("NOT_A_PDF", "File name must end in .pdf.")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise PdfRejected("NOT_A_PDF", f"Content type must be application/pdf, got {declared!r}.")
    if not head.startswith(PDF_MAGIC):
        raise PdfRejected("NOT_A_PDF", "File does not start with %PDF-.")


def extract_text(path: Path, max_pages: int) -> PdfText:
    """Text of every page in reading order (top to bottom, left to right)."""
    try:
        with pdfplumber.open(path) as pdf:
            if pdf.doc.encryption is not None:
                raise PdfRejected("ENCRYPTED_PDF", "Encrypted PDFs are not supported.")
            if len(pdf.pages) > max_pages:
                raise PdfRejected(
                    "TOO_MANY_PAGES", f"PDF has {len(pdf.pages)} pages; the limit is {max_pages}."
                )
            pages = [page.extract_text() or "" for page in pdf.pages]
    except PdfRejected:
        raise
    except Exception as error:  # pdfplumber wraps pdfminer errors in PdfminerException
        cause = error.args[0] if isinstance(error, PdfminerException) and error.args else error
        if isinstance(cause, PDFPasswordIncorrect | PDFEncryptionError):
            raise PdfRejected("ENCRYPTED_PDF", "Encrypted PDFs are not supported.") from error
        raise PdfRejected("INVALID_PDF", "The file is not a readable PDF.") from error

    if not pages:
        raise PdfRejected("INVALID_PDF", "The PDF has no pages.")
    visible = sum(len("".join(page.split())) for page in pages)
    if visible < MIN_CHARS_PER_PAGE * len(pages):
        raise PdfRejected(
            "SCANNED_PDF_UNSUPPORTED",
            "No usable text layer (scanned or image-only PDF). Only text-based PDFs are supported.",
        )
    return PdfText(pages=pages)
