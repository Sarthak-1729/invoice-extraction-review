"""Turn canonical values (Decimal, date) into the strings printed on a PDF."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

DateStyle = Literal["us_slash", "eu_slash", "dotted", "iso", "long_mdy", "long_dmy", "short_dmy"]
NumberStyle = Literal["us", "eu", "space", "swiss", "indian", "plain"]
CurrencyDisplay = Literal["symbol_prefix", "symbol_suffix", "code_prefix", "code_suffix", "none"]

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]  # fmt: skip

# Helvetica (the built-in PDF font) has no ₹ glyph, so INR uses "Rs.".
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "Rs.", "CAD": "C$", "AUD": "A$"}
MINOR_UNITS = {"JPY": 0}

# (thousands separator, decimal separator)
_SEPARATORS = {
    "us": (",", "."),
    "eu": (".", ","),
    "space": (" ", ","),
    "swiss": ("'", "."),
    "indian": (",", "."),
    "plain": ("", "."),
}


def minor_units(currency: str) -> int:
    return MINOR_UNITS.get(currency, 2)


def quantize(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def format_date(value: date, style: DateStyle) -> str:
    month = MONTHS[value.month - 1]
    return {
        "us_slash": f"{value.month:02d}/{value.day:02d}/{value.year}",
        "eu_slash": f"{value.day:02d}/{value.month:02d}/{value.year}",
        "dotted": f"{value.day:02d}.{value.month:02d}.{value.year}",
        "iso": value.isoformat(),
        "long_mdy": f"{month} {value.day}, {value.year}",
        "long_dmy": f"{value.day} {month} {value.year}",
        "short_dmy": f"{value.day:02d}-{month[:3]}-{value.year}",
    }[style]


def _group(integer: str, style: NumberStyle) -> list[str]:
    if style == "indian" and len(integer) > 3:
        head, last = integer[:-3], integer[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        return [head, *groups, last]
    groups = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return [integer, *groups]


def format_number(value: Decimal, style: NumberStyle, places: int | None = None) -> str:
    """Format with a fixed number of decimals, or as few as needed when places is None."""
    if places is not None:
        value = quantize(value, places)
    elif value == value.to_integral_value():
        value = value.quantize(Decimal(1))
    else:
        value = value.normalize()
    sign = "-" if value < 0 else ""
    integer, _, fraction = f"{abs(value):f}".partition(".")
    thousands, decimal = _SEPARATORS[style]
    grouped = thousands.join(_group(integer, style))
    return sign + grouped + (decimal + fraction if fraction else "")


def format_money(value: Decimal, currency: str, style: NumberStyle, display: CurrencyDisplay):
    number = format_number(value, style, minor_units(currency))
    symbol = SYMBOLS.get(currency, currency)
    if display == "symbol_prefix":
        separator = " " if symbol[-1].isalpha() or symbol.endswith(".") else ""
        return f"{symbol}{separator}{number}"
    if display == "symbol_suffix":
        return f"{number} {symbol}"
    if display == "code_prefix":
        return f"{currency} {number}"
    if display == "code_suffix":
        return f"{number} {currency}"
    return number


def format_percent(rate: Decimal, style: NumberStyle) -> str:
    return f"{format_number(rate * 100, style)}%"
