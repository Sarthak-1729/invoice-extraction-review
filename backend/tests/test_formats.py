from datetime import date
from decimal import Decimal

import pytest

from app.validation.flags import FlagCode
from app.validation.formats import (
    currency_from_amounts,
    detect_date_order,
    detect_decimal_separator,
    minor_units,
    parse_amount,
    parse_currency,
    parse_date,
)

# ---------------------------------------------------------------- amounts


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234", "1234"),
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("1'234.56", "1234.56"),
        ("1 234,56", "1234.56"),  # non-breaking space
        ("1,234,567", "1234567"),
        ("1.234.567,89", "1234567.89"),
        ("1,23,456.00", "123456.00"),  # Indian grouping
        ("12,50", "12.50"),
        ("0,500", "0.500"),
        (".50", "0.50"),
        ("12345.678", "12345.678"),
        ("$1,234.56", "1234.56"),
        ("€ 1.234,56", "1234.56"),
        ("1.234,56 €", "1234.56"),
        ("USD 99.00", "99.00"),
        ("Rs. 1,23,456.00", "123456.00"),
        ("(12.00)", "-12.00"),
        ("-12.00", "-12.00"),
        ("−12.00", "-12.00"),  # unicode minus
        ("12.00-", "-12.00"),
        ("2 hrs", "2"),
        ("2.5", "2.5"),
    ],
)
def test_parse_amount_valid(raw, expected):
    parsed = parse_amount(raw)
    assert parsed.code is None
    assert parsed.value == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "12-34", "1,2,3.00", "1.234.56", "12 50", "--", "1.2,3.4"])
def test_parse_amount_unparseable(raw):
    parsed = parse_amount(raw)
    assert parsed.value is None
    assert parsed.code == FlagCode.AMOUNT_UNPARSEABLE


def test_parse_amount_none_is_not_flagged():
    assert parse_amount(None).value is None
    assert parse_amount(None).code is None


@pytest.mark.parametrize("raw", ["1,234", "1.234"])
def test_single_separator_with_three_digits_is_ambiguous_without_hint(raw):
    parsed = parse_amount(raw)
    assert parsed.value is None
    assert parsed.code == FlagCode.NUMBER_FORMAT_AMBIGUOUS


def test_ambiguous_amount_resolved_by_document_hint():
    assert parse_amount("1,234", decimal_hint=".").value == Decimal("1234")
    assert parse_amount("1,234", decimal_hint=",").value == Decimal("1.234")
    assert parse_amount("1.234", decimal_hint=",").value == Decimal("1234")


def test_zero_decimal_currency_treats_separator_as_thousands():
    assert parse_amount("¥12,000", minor=0).value == Decimal("12000")


def test_detect_decimal_separator():
    assert detect_decimal_separator(["1.234,56", "1,234", None]) == ","
    assert detect_decimal_separator(["12.50", "1,234"]) == "."
    assert detect_decimal_separator(["1,234", "100"]) is None
    assert detect_decimal_separator(["12.50", "12,50"]) is None  # conflicting


def test_minor_units():
    assert minor_units("EUR") == 2
    assert minor_units("JPY") == 0
    assert minor_units("KWD") == 3
    assert minor_units(None) == 2


# ------------------------------------------------------------------ dates


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-04-03", date(2026, 4, 3)),
        ("2026/04/03", date(2026, 4, 3)),
        ("25/03/2026", date(2026, 3, 25)),
        ("03/25/2026", date(2026, 3, 25)),
        ("03.04.2026", date(2026, 4, 3)),  # dotted = day first
        ("05/05/2026", date(2026, 5, 5)),
        ("3 April 2026", date(2026, 4, 3)),
        ("3rd Apr 2026", date(2026, 4, 3)),
        ("03-Apr-2026", date(2026, 4, 3)),
        ("April 3, 2026", date(2026, 4, 3)),
        ("Sept 30, 2026", date(2026, 9, 30)),
        ("25/03/26", date(2026, 3, 25)),
    ],
)
def test_parse_date_valid(raw, expected):
    parsed = parse_date(raw)
    assert parsed.code is None
    assert parsed.value == expected


@pytest.mark.parametrize(
    "raw", ["31/02/2026", "2026-13-01", "next Tuesday", "3 Foo 2026", "13/13/2026"]
)
def test_parse_date_unparseable(raw):
    parsed = parse_date(raw)
    assert parsed.value is None
    assert parsed.code == FlagCode.DATE_UNPARSEABLE


def test_ambiguous_date_is_flagged_not_guessed():
    parsed = parse_date("03/04/2026")
    assert parsed.value is None
    assert parsed.code == FlagCode.DATE_AMBIGUOUS


def test_ambiguous_date_resolved_by_hint():
    assert parse_date("03/04/2026", order_hint="DMY").value == date(2026, 4, 3)
    assert parse_date("03/04/2026", order_hint="MDY").value == date(2026, 3, 4)


def test_detect_date_order():
    assert detect_date_order(["03/04/2026", "25/04/2026"]) == "DMY"
    assert detect_date_order(["03/04/2026", "04/25/2026"]) == "MDY"
    assert detect_date_order(["03/04/2026", None]) is None
    assert detect_date_order(["2026-04-03"]) is None


# ------------------------------------------------------------- currencies


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EUR", "EUR"),
        ("usd", "USD"),
        ("€", "EUR"),
        ("US$", "USD"),
        ("Rs.", "INR"),
        ("₹", "INR"),
        ("Euro (EUR)", "EUR"),
        ("Euro (€)", "EUR"),
    ],
)
def test_parse_currency_valid(raw, expected):
    assert parse_currency(raw).value == expected


@pytest.mark.parametrize("raw", ["$", "¥", "kr"])
def test_parse_currency_ambiguous(raw):
    parsed = parse_currency(raw)
    assert parsed.value is None
    assert parsed.code == FlagCode.CURRENCY_AMBIGUOUS


@pytest.mark.parametrize("raw", ["XYZ", "dollars", "USD/EUR"])
def test_parse_currency_unknown(raw):
    assert parse_currency(raw).code == FlagCode.CURRENCY_UNKNOWN


def test_currency_from_amounts():
    assert currency_from_amounts(["€ 12,00", "5,00 €"]).value == "EUR"
    assert currency_from_amounts(["$12.00"]).code == FlagCode.CURRENCY_AMBIGUOUS
    assert currency_from_amounts(["€12", "£5"]).code == FlagCode.CURRENCY_AMBIGUOUS
    assert currency_from_amounts(["12.00", None]) is None
