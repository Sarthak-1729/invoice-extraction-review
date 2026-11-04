"""Ground-truth JSON for one invoice.

Each field stores the canonical ``value`` (what a perfect extractor should
return after normalization) and the exact ``printed`` string on the PDF. For
documents with deliberate arithmetic errors, the truth is what is printed:
the document is wrong, not the extraction.
"""

import dataclasses
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from eval.generator.spec import InvoiceSpec

SCHEMA_VERSION = 1


def _field(value: Any, printed: str | None) -> dict[str, Any]:
    return {"value": None if value is None else str(value), "printed": printed}


def truth_dict(spec: InvoiceSpec, wrapped_line_items: list[int] | None = None) -> dict[str, Any]:
    """``wrapped_line_items``: indices whose description the PDF text layer splits
    (only for the deliberate wrapped_descriptions feature; filled after rendering)."""

    def money(value: Decimal | None) -> dict[str, Any]:
        return _field(value, None if value is None else spec.money(value))

    def day(value):
        return _field(value and value.isoformat(), value and spec.day(value))

    config = dataclasses.asdict(spec.config)
    config["tax_rate"] = None if spec.config.tax_rate is None else str(spec.config.tax_rate)

    return {
        "schema_version": SCHEMA_VERSION,
        "doc_id": spec.config.doc_id,
        "layout": spec.config.layout,
        "features": spec.features,
        "arithmetic_consistent": spec.arithmetic_consistent,
        "fields": {
            "invoice_number": _field(spec.invoice_number, spec.invoice_number),
            "vendor_name": _field(spec.vendor_name, spec.vendor_name),
            "bill_to_name": _field(spec.bill_to_name, spec.bill_to_name),
            "invoice_date": day(spec.invoice_date),
            "due_date": day(spec.due_date),
            "currency": _field(spec.config.currency, spec.currency_printed()),
            "subtotal": money(spec.subtotal),
            "tax": money(spec.tax),
            "total": money(spec.total),
        },
        "line_items": [
            {
                "description": _field(line.description, line.description),
                "quantity": _field(line.quantity, spec.quantity(line.quantity)),
                "unit_price": _field(line.unit_price, spec.unit_price(line.unit_price)),
                "amount": _field(line.amount, spec.money(line.amount)),
            }
            for line in spec.lines
        ],
        "wrapped_line_items": wrapped_line_items or [],
        "generator_config": config,
    }


def write_truth(truth: dict[str, Any], path: Path) -> None:
    text = json.dumps(truth, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
