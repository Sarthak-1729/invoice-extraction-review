"""Flag model and reason codes shown to reviewers.

Flags come only from deterministic checks; the LLM's self-reported confidence
is never used.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class FlagCode(StrEnum):
    # Arithmetic
    LINE_AMOUNT_MISMATCH = "LINE_AMOUNT_MISMATCH"
    SUBTOTAL_MISMATCH = "SUBTOTAL_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    # Grounding
    VALUE_NOT_IN_DOCUMENT = "VALUE_NOT_IN_DOCUMENT"
    # Format
    DATE_UNPARSEABLE = "DATE_UNPARSEABLE"
    DATE_AMBIGUOUS = "DATE_AMBIGUOUS"
    AMOUNT_UNPARSEABLE = "AMOUNT_UNPARSEABLE"
    NUMBER_FORMAT_AMBIGUOUS = "NUMBER_FORMAT_AMBIGUOUS"
    CURRENCY_UNKNOWN = "CURRENCY_UNKNOWN"
    CURRENCY_AMBIGUOUS = "CURRENCY_AMBIGUOUS"
    # Consistency
    DUE_BEFORE_INVOICE_DATE = "DUE_BEFORE_INVOICE_DATE"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    LINE_ITEMS_EMPTY = "LINE_ITEMS_EMPTY"
    # Optional / pipeline
    RUN_DISAGREEMENT = "RUN_DISAGREEMENT"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Flag(BaseModel):
    model_config = ConfigDict(frozen=True)

    field_path: str
    code: FlagCode
    severity: Severity
    message: str


_DEFAULTS: dict[FlagCode, tuple[Severity, str]] = {
    FlagCode.LINE_AMOUNT_MISMATCH: (
        Severity.ERROR,
        "Quantity × unit price does not match the amount.",
    ),
    FlagCode.SUBTOTAL_MISMATCH: (Severity.ERROR, "Line amounts do not add up to the subtotal."),
    FlagCode.TOTAL_MISMATCH: (Severity.ERROR, "Subtotal plus tax does not match the total."),
    FlagCode.VALUE_NOT_IN_DOCUMENT: (Severity.ERROR, "This value was not found in the document."),
    FlagCode.DATE_UNPARSEABLE: (Severity.ERROR, "This is not a valid date."),
    FlagCode.DATE_AMBIGUOUS: (
        Severity.WARNING,
        "Day and month order is unclear (for example 03/04 could be 3 April or 4 March).",
    ),
    FlagCode.AMOUNT_UNPARSEABLE: (Severity.ERROR, "This is not a valid number."),
    FlagCode.NUMBER_FORMAT_AMBIGUOUS: (
        Severity.WARNING,
        "Unclear whether the separator is a thousands or a decimal separator.",
    ),
    FlagCode.CURRENCY_UNKNOWN: (Severity.ERROR, "Not a recognized ISO 4217 currency."),
    FlagCode.CURRENCY_AMBIGUOUS: (
        Severity.WARNING,
        "The currency symbol is used by several currencies (for example $).",
    ),
    FlagCode.DUE_BEFORE_INVOICE_DATE: (
        Severity.WARNING,
        "The due date is before the invoice date.",
    ),
    FlagCode.REQUIRED_FIELD_MISSING: (Severity.ERROR, "This required field was not found."),
    FlagCode.LINE_ITEMS_EMPTY: (Severity.WARNING, "No line items were extracted."),
    FlagCode.RUN_DISAGREEMENT: (Severity.WARNING, "Two extraction runs disagree on this value."),
    FlagCode.SCHEMA_VALIDATION_FAILED: (
        Severity.ERROR,
        "The model output did not match the expected schema.",
    ),
}


def make_flag(field_path: str, code: FlagCode, message: str | None = None) -> Flag:
    severity, default_message = _DEFAULTS[code]
    return Flag(
        field_path=field_path, code=code, severity=severity, message=message or default_message
    )
