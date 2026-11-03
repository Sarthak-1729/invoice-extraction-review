"""Turn a validated RawExtraction (strings as printed) into a typed Invoice.

Every value that cannot be parsed with certainty becomes None plus a flag, so a
reviewer sees it instead of a silently wrong number.
"""

from dataclasses import dataclass, field

from app.schemas.invoice import Invoice, LineItem, RawExtraction
from app.validation.flags import Flag, make_flag
from app.validation.formats import (
    ParsedAmount,
    ParsedCurrency,
    ParsedDate,
    clean_text,
    currency_from_amounts,
    detect_date_order,
    detect_decimal_separator,
    minor_units,
    parse_amount,
    parse_currency,
    parse_date,
)


@dataclass
class NormalizationResult:
    invoice: Invoice
    flags: list[Flag] = field(default_factory=list)


def _numeric_raws(raw: RawExtraction) -> list[str | None]:
    values = [raw.subtotal, raw.tax, raw.total]
    for item in raw.line_items:
        values += [item.quantity, item.unit_price, item.amount]
    return values


def _resolve_currency(raw: RawExtraction) -> ParsedCurrency | None:
    """Use the printed currency; fall back to symbols next to amounts when it is
    missing, ambiguous or unknown."""
    printed = parse_currency(raw.currency) if raw.currency is not None else None
    if printed is not None and printed.value is not None:
        return printed
    from_amounts = currency_from_amounts(_numeric_raws(raw))
    if from_amounts is not None and from_amounts.value is not None:
        return from_amounts
    return printed or from_amounts


def normalize(raw: RawExtraction) -> NormalizationResult:
    flags: list[Flag] = []

    def keep(path: str, parsed: ParsedAmount | ParsedDate | ParsedCurrency):
        if parsed.code is not None:
            flags.append(make_flag(path, parsed.code))
        return parsed.value

    currency_result = _resolve_currency(raw)
    currency = keep("currency", currency_result) if currency_result else None
    minor = minor_units(currency)
    decimal_hint = detect_decimal_separator(_numeric_raws(raw))
    order_hint = detect_date_order([raw.invoice_date, raw.due_date])

    def amount(path: str, value: str | None):
        return keep(path, parse_amount(value, decimal_hint, minor))

    def day(path: str, value: str | None):
        return keep(path, parse_date(value, order_hint))

    invoice = Invoice(
        invoice_number=clean_text(raw.invoice_number),
        vendor_name=clean_text(raw.vendor_name),
        bill_to_name=clean_text(raw.bill_to_name),
        invoice_date=day("invoice_date", raw.invoice_date),
        due_date=day("due_date", raw.due_date),
        currency=currency,
        subtotal=amount("subtotal", raw.subtotal),
        tax=amount("tax", raw.tax),
        total=amount("total", raw.total),
        line_items=[
            LineItem(
                description=clean_text(item.description),
                quantity=amount(f"line_items[{i}].quantity", item.quantity),
                unit_price=amount(f"line_items[{i}].unit_price", item.unit_price),
                amount=amount(f"line_items[{i}].amount", item.amount),
            )
            for i, item in enumerate(raw.line_items)
        ],
    )
    return NormalizationResult(invoice=invoice, flags=flags)
