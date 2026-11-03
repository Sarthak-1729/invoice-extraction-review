"""Invoice schemas.

Two layers:
- ``RawExtraction`` is what the LLM returns: every value is the string exactly as
  printed in the document, or None. It is untrusted until validated.
- ``Invoice`` is built from it by deterministic code (``app.normalize``):
  real dates, Decimal money and ISO 4217 currency codes.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

MAX_TEXT_LENGTH = 500
MAX_LINE_ITEMS = 500


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


RawText = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_TEXT_LENGTH)] | None,
    BeforeValidator(_blank_to_none),
]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class RawLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: RawText = None
    quantity: RawText = None
    unit_price: RawText = None
    amount: RawText = None


class RawExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: RawText = None
    vendor_name: RawText = None
    bill_to_name: RawText = None
    invoice_date: RawText = None
    due_date: RawText = None
    currency: RawText = None
    subtotal: RawText = None
    tax: RawText = None
    total: RawText = None
    line_items: list[RawLineItem] = Field(default_factory=list, max_length=MAX_LINE_ITEMS)


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class Invoice(BaseModel):
    invoice_number: str | None = None
    vendor_name: str | None = None
    bill_to_name: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: CurrencyCode | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    line_items: list[LineItem] = Field(default_factory=list)
