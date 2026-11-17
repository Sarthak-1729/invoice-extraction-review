"""Grounding check: every extracted value must occur in the PDF text.

Whitespace rule (decided in Phase 3 from the dev text layers):
- Both sides: Unicode NFKC, every whitespace run (spaces, newlines) collapsed
  to one space. Whitespace is never removed, so a value with a missing or
  extra space ("matteblack") is not grounded.
- Contiguous match for every field, on word boundaries like a regex ``\\b``:
  where the value starts or ends with a letter or digit, the neighboring text
  character must not be one ("INV-104" is not found inside "INV-10423", but
  "$" is found in "$3,677.00").
- ``description`` only, when there is no contiguous match: a wrapped table
  cell is accepted if the value's whole words appear in order as contiguous
  segments on consecutive text lines (at most ``MAX_WRAP_LINES``). Text
  stitched together across a skipped line is not accepted.

Limit: grounding catches invented values, not misplaced ones. A value copied
from the wrong place in the document (an item code inside a description) is
still in the text and passes.
"""

import unicodedata

from app.schemas.invoice import RawExtraction
from app.validation.flags import Flag, FlagCode, make_flag

MAX_WRAP_LINES = 4
HEADER_FIELDS = (
    "invoice_number",
    "vendor_name",
    "bill_to_name",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax",
    "total",
)
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")


def collapse(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


class DocumentText:
    """The PDF text, prepared once for many lookups."""

    def __init__(self, text: str) -> None:
        self.flat = collapse(text)
        self.lines = [collapse(line).split() for line in text.splitlines()]
        self.lines = [tokens for tokens in self.lines if tokens]

    def contains(self, value: str) -> bool:
        needle = collapse(value)
        if not needle:
            return True
        start = self.flat.find(needle)
        while start != -1:
            end = start + len(needle)
            before = self.flat[start - 1] if start > 0 else " "
            after = self.flat[end] if end < len(self.flat) else " "
            # Like a regex \b: a boundary is needed only where the value itself
            # starts or ends with a letter or digit ("$" may touch "3,677.00").
            left_ok = not (needle[0].isalnum() and before.isalnum())
            right_ok = not (needle[-1].isalnum() and after.isalnum())
            if left_ok and right_ok:
                return True
            start = self.flat.find(needle, start + 1)
        return False

    def contains_wrapped(self, value: str) -> bool:
        words = collapse(value).split()
        if not words:
            return True
        for first in range(len(self.lines)):
            for start in range(len(self.lines[first])):
                if self._wrapped_from(words, first, start):
                    return True
        return False

    def _wrapped_from(self, words: list[str], line_index: int, start: int) -> bool:
        """Match ``words`` beginning at ``lines[line_index][start]``, continuing
        on the following lines (each continuation may start anywhere in its
        line, e.g. after an item-code cell)."""
        position = 0
        for offset in range(MAX_WRAP_LINES):
            index = line_index + offset
            if index >= len(self.lines):
                return False
            tokens = self.lines[index]
            starts = [start] if offset == 0 else range(len(tokens))
            best = max((_run(tokens, s, words, position) for s in starts), default=0)
            if best == 0:
                return False
            position += best
            if position == len(words):
                return True
        return False


def _run(tokens: list[str], start: int, words: list[str], position: int) -> int:
    """How many of ``words[position:]`` match ``tokens`` from ``start`` on."""
    count = 0
    while (
        start + count < len(tokens)
        and position + count < len(words)
        and tokens[start + count] == words[position + count]
    ):
        count += 1
    return count


def is_grounded(value: str, document: DocumentText, field: str) -> bool:
    if document.contains(value):
        return True
    return field == "description" and document.contains_wrapped(value)


def check_grounding(raw: RawExtraction, document_text: str) -> list[Flag]:
    document = DocumentText(document_text)
    flags = []
    for name in HEADER_FIELDS:
        value = getattr(raw, name)
        if value is not None and not is_grounded(value, document, name):
            flags.append(make_flag(name, FlagCode.VALUE_NOT_IN_DOCUMENT))
    for index, line in enumerate(raw.line_items):
        for name in LINE_FIELDS:
            value = getattr(line, name)
            if value is not None and not is_grounded(value, document, name):
                flags.append(
                    make_flag(f"line_items[{index}].{name}", FlagCode.VALUE_NOT_IN_DOCUMENT)
                )
    return flags
