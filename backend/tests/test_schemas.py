import pytest
from pydantic import ValidationError

from app.schemas.invoice import MAX_TEXT_LENGTH, Invoice, RawExtraction


def test_raw_extraction_accepts_strings_and_nulls():
    raw = RawExtraction.model_validate(
        {
            "invoice_number": " INV-001 ",
            "total": "1,234.56",
            "tax": None,
            "line_items": [{"description": "Widget", "amount": "10.00"}],
        }
    )
    assert raw.invoice_number == "INV-001"
    assert raw.tax is None
    assert raw.line_items[0].quantity is None


def test_blank_strings_become_none():
    raw = RawExtraction.model_validate({"vendor_name": "   ", "due_date": ""})
    assert raw.vendor_name is None
    assert raw.due_date is None


def test_unknown_keys_are_rejected():
    # The model must not smuggle extra fields (e.g. injected instructions) through.
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"total": "1", "approved": "true"})
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"line_items": [{"amount": "1", "note": "x"}]})


def test_non_string_values_are_rejected():
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"total": 12.5})


def test_overlong_text_is_rejected():
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({"vendor_name": "x" * (MAX_TEXT_LENGTH + 1)})


def test_invoice_currency_must_be_three_uppercase_letters():
    assert Invoice(currency="EUR").currency == "EUR"
    with pytest.raises(ValidationError):
        Invoice(currency="euro")
