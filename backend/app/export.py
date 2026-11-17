"""Export approved documents as JSON, or CSV with one row per line item.

Only approved documents are exported (never failed ones). Values are the
normalized values. CSV cells that a spreadsheet would run as a formula are
prefixed with an apostrophe, because the values come from untrusted PDFs.
"""

import csv
import io
import re
from typing import Any

from app.db import Document

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
CSV_COLUMNS = (
    "document_id",
    "file_name",
    "approved_at",
    *HEADER_FIELDS,
    "line_number",
    *LINE_FIELDS,
)
_FORMULA = re.compile(r"^[=+@\t\r]|^-(?![\d.])")


def export_record(document: Document) -> dict[str, Any]:
    normalized = document.normalized or {}
    return {
        "document_id": document.id,
        "file_name": document.display_name,
        "approved_at": document.approved_at.isoformat() if document.approved_at else None,
        "acknowledged_open_flags": document.acknowledged_open_flags,
        **{name: normalized.get(name) for name in HEADER_FIELDS},
        "line_items": [
            {name: line.get(name) for name in LINE_FIELDS}
            for line in normalized.get("line_items") or []
        ],
    }


def safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if _FORMULA.match(text) else text


def export_csv(documents: list[Document]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for document in documents:
        record = export_record(document)
        header = [record["document_id"], record["file_name"], record["approved_at"]]
        header += [record[name] for name in HEADER_FIELDS]
        lines = record["line_items"] or [None]  # a document without lines still gets a row
        for number, line in enumerate(lines, 1):
            values = [number, *(line[name] for name in LINE_FIELDS)] if line else [""] * 5
            writer.writerow([safe_cell(v) for v in [*header, *values]])
    return buffer.getvalue()
