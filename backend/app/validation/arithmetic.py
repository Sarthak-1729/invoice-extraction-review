"""Arithmetic checks: line amount = qty × price, sum of lines = subtotal,
subtotal + tax = total.

Tolerance is one minor unit of the currency (0.01 for EUR, 1 for JPY). A flag
is attached to every field in the failing equation; a subtotal mismatch flags
the line-item table as a whole (path ``line_items``) rather than every line.
"""

from decimal import Decimal

from app.schemas.invoice import Invoice
from app.validation.flags import Flag, FlagCode, make_flag
from app.validation.formats import minor_units


def _money(value: Decimal, unit: Decimal) -> str:
    return str(value.quantize(unit))


def check_arithmetic(invoice: Invoice) -> list[Flag]:
    unit = Decimal(1).scaleb(-minor_units(invoice.currency))
    flags: list[Flag] = []

    for i, item in enumerate(invoice.line_items):
        if item.quantity is None or item.unit_price is None or item.amount is None:
            continue
        expected = item.quantity * item.unit_price
        if abs(expected - item.amount) > unit:
            message = (
                f"Quantity × unit price = {_money(expected, unit)}, "
                f"but the amount is {item.amount}."
            )
            flags += [
                make_flag(f"line_items[{i}].{name}", FlagCode.LINE_AMOUNT_MISMATCH, message)
                for name in ("quantity", "unit_price", "amount")
            ]

    amounts = [item.amount for item in invoice.line_items]
    lines_sum = (
        sum(amounts, Decimal(0)) if amounts and all(a is not None for a in amounts) else None
    )

    if (
        invoice.subtotal is not None
        and lines_sum is not None
        and abs(lines_sum - invoice.subtotal) > unit
    ):
        message = (
            f"Line amounts add up to {_money(lines_sum, unit)}, "
            f"but the subtotal is {invoice.subtotal}."
        )
        flags += [
            make_flag(path, FlagCode.SUBTOTAL_MISMATCH, message)
            for path in ("subtotal", "line_items")
        ]

    base, base_path = (
        (invoice.subtotal, "subtotal")
        if invoice.subtotal is not None
        else (lines_sum, "line_items")
    )
    if invoice.total is not None and base is not None:
        expected = base + (invoice.tax or Decimal(0))
        if abs(expected - invoice.total) > unit:
            tax_text = f" + tax {invoice.tax}" if invoice.tax is not None else ""
            message = (
                f"{base_path.replace('_', ' ').capitalize()} {_money(base, unit)}{tax_text} "
                f"= {_money(expected, unit)}, but the total is {invoice.total}."
            )
            paths = [base_path, *(["tax"] if invoice.tax is not None else []), "total"]
            flags += [make_flag(path, FlagCode.TOTAL_MISMATCH, message) for path in paths]

    return flags
