"""Check that a rendered PDF has a text layer containing every printed truth string.

If a printed value is missing from the extracted text, the label could never be
grounded, so generation fails loudly instead of producing a broken dataset.
"""

import unicodedata
from pathlib import Path
from typing import Any

import pdfplumber


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def pdf_text(path: Path) -> tuple[str, int]:
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages), len(pages)


def printed_values(truth: dict[str, Any]) -> list[tuple[str, str]]:
    values = [(name, f["printed"]) for name, f in truth["fields"].items() if f["printed"]]
    for i, item in enumerate(truth["line_items"]):
        values += [
            (f"line_items[{i}].{name}", f["printed"]) for name, f in item.items() if f["printed"]
        ]
    return values


def missing_values(pdf_path: Path, truth: dict[str, Any]) -> list[str]:
    text, _ = pdf_text(pdf_path)
    haystack = _normalize(text)
    return [
        f"{path}: {printed!r}"
        for path, printed in printed_values(truth)
        if _normalize(printed) not in haystack
    ]
