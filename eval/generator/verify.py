"""Check that a rendered PDF has a text layer containing every printed truth string.

Every printed value must appear contiguously in the extracted text, so it can be
grounded. The one exception is the deliberate ``wrapped_descriptions`` feature:
a description that wraps inside its table cell is split by the text layer, so it
is accepted when its words appear in order nearby, and reported as wrapped.
"""

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber

WRAP_FEATURE = "wrapped_descriptions"


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


def _words_in_order(words: list[str], haystack: str, max_span: int) -> bool:
    """True if the words appear in order within ``max_span`` characters."""
    start = haystack.find(words[0])
    while start != -1:
        position = start + len(words[0])
        for word in words[1:]:
            position = haystack.find(word, position)
            if position == -1:
                return False
            position += len(word)
        if position - start <= max_span:
            return True
        start = haystack.find(words[0], start + 1)
    return False


@dataclass
class TextLayerCheck:
    missing: list[str] = field(default_factory=list)  # "path: 'printed'"
    wrapped_line_items: list[int] = field(default_factory=list)


def check_text_layer(pdf_path: Path, truth: dict[str, Any]) -> TextLayerCheck:
    text, _ = pdf_text(pdf_path)
    haystack = _normalize(text)
    wrap_allowed = WRAP_FEATURE in truth["features"]
    result = TextLayerCheck()

    for path, printed in printed_values(truth):
        needle = _normalize(printed)
        if needle in haystack:
            continue
        # Wrapped rows interleave other cells, so allow generous slack.
        if (
            wrap_allowed
            and path.endswith(".description")
            and _words_in_order(needle.split(), haystack, max_span=len(needle) + 200)
        ):
            result.wrapped_line_items.append(int(path.split("[")[1].split("]")[0]))
            continue
        result.missing.append(f"{path}: {printed!r}")

    if wrap_allowed and not result.wrapped_line_items:
        result.missing.append(f"{WRAP_FEATURE} is set but no description wrapped")
    return result
