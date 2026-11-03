"""Consistency checks: required fields present, line items present, due date order."""

from app.schemas.invoice import Invoice, RawExtraction
from app.validation.flags import Flag, FlagCode, make_flag

REQUIRED_FIELDS = {
    "invoice_number": "Invoice number",
    "vendor_name": "Vendor name",
    "invoice_date": "Invoice date",
    "total": "Total",
}


def check_consistency(raw: RawExtraction, invoice: Invoice) -> list[Flag]:
    # Missing is judged on the raw value: a value that was printed but could not
    # be parsed already carries a format flag.
    flags = [
        make_flag(name, FlagCode.REQUIRED_FIELD_MISSING, f"{label} is required but was not found.")
        for name, label in REQUIRED_FIELDS.items()
        if getattr(raw, name) is None
    ]
    if not raw.line_items:
        flags.append(make_flag("line_items", FlagCode.LINE_ITEMS_EMPTY))
    if invoice.invoice_date and invoice.due_date and invoice.due_date < invoice.invoice_date:
        flags.append(make_flag("due_date", FlagCode.DUE_BEFORE_INVOICE_DATE))
    return flags
