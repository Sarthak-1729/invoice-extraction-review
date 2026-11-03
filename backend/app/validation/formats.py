"""Parse amounts, dates and currencies exactly as printed on an invoice.

Each parser returns either a value or a flag code. Ambiguous input returns
``value=None`` with an ``*_AMBIGUOUS`` code: we flag, we never guess. Callers
may pass a document-level hint (decimal separator, day/month order) learned
from other, unambiguous values in the same document.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from app.validation.flags import FlagCode

DecimalSeparator = Literal[",", "."]
DateOrder = Literal["DMY", "MDY"]

# Active ISO 4217 codes (as of 2025).
ISO_4217 = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD
    BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN
    ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD
    IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD
    MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD
    OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP
    SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD
    UYU UZS VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG
    """.split()
)
_ZERO_DECIMAL = frozenset("BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX VND VUV XAF XOF XPF".split())
_THREE_DECIMAL = frozenset("BHD IQD JOD KWD LYD OMR TND".split())

_CURRENCY_SYMBOLS = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "RS": "INR",
    "RS.": "INR",
    "US$": "USD",
    "A$": "AUD",
    "AU$": "AUD",
    "C$": "CAD",
    "CA$": "CAD",
    "NZ$": "NZD",
    "HK$": "HKD",
    "S$": "SGD",
    "R$": "BRL",
}
_AMBIGUOUS_SYMBOLS = frozenset({"$", "¥", "KR", "KR."})
_SINGLE_CHAR_SYMBOLS = {"€": "EUR", "£": "GBP", "₹": "INR"}


def minor_units(currency: str | None) -> int:
    """Number of decimal places for a currency (2 when unknown)."""
    if currency in _ZERO_DECIMAL:
        return 0
    if currency in _THREE_DECIMAL:
        return 3
    return 2


def clean_text(raw: str | None) -> str | None:
    """Unicode-normalize (NFKC) and collapse whitespace; empty becomes None."""
    if raw is None:
        return None
    text = " ".join(unicodedata.normalize("NFKC", raw).split())
    return text or None


# ---------------------------------------------------------------- amounts


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal | None
    code: FlagCode | None = None
    # Set only when this string alone proves which character is the decimal separator.
    decimal_separator: DecimalSeparator | None = None


_THOUSANDS_SPACES = " '’"
_LEADING_WORD = re.compile(r"^[A-Za-z][A-Za-z.]*\s*")
_TRAILING_WORD = re.compile(r"\s*[A-Za-z][A-Za-z.]*$")
_NUMBER_CHARS = re.compile(r"[\d.,'’ ]+")
_UNPARSEABLE = ParsedAmount(None, FlagCode.AMOUNT_UNPARSEABLE)


def _strip_words(text: str) -> str:
    """Remove a leading/trailing currency code or unit word ("USD", "Rs.", "hrs")."""
    return _TRAILING_WORD.sub("", _LEADING_WORD.sub("", text.strip())).strip()


def _valid_grouping(groups: list[str], separator: str) -> bool:
    """Western (1,234,567) or Indian (12,34,567) digit grouping."""
    if not all(group.isdigit() for group in groups):
        return False
    head, *rest = groups
    if not rest:
        return True
    western = 1 <= len(head) <= 3 and all(len(group) == 3 for group in rest)
    indian = (
        separator == ","
        and len(rest[-1]) == 3
        and 1 <= len(head) <= 2
        and all(len(group) == 2 for group in rest[:-1])
    )
    return western or indian


def parse_amount(
    raw: str | None,
    decimal_hint: DecimalSeparator | None = None,
    minor: int = 2,
) -> ParsedAmount:
    """Parse "1,234.56", "1.234,56 €", "(12.00)", "1,23,456.00", "¥ 12,000", "2 hrs"."""
    text = clean_text(raw)
    if text is None:
        return ParsedAmount(None)

    text = text.replace("−", "-")
    for symbol in "$€£₹¥":
        text = text.replace(symbol, "")
    text = _strip_words(text)

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.startswith("-") or text.endswith("-"):
        negative, text = True, text.strip("-")
    text = _strip_words(text.lstrip("+"))

    if not text or not _NUMBER_CHARS.fullmatch(text) or not any(c.isdigit() for c in text):
        return _UNPARSEABLE

    has_space = any(c in _THOUSANDS_SPACES for c in text)
    for c in _THOUSANDS_SPACES:
        text = text.replace(c, " ")

    decimal: str | None
    thousands: str | None
    proven: DecimalSeparator | None = None
    commas, dots = text.count(","), text.count(".")

    if commas and dots:
        proven = decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        if text.count(decimal) > 1 or has_space:
            return _UNPARSEABLE
    elif commas or dots:
        sep: DecimalSeparator = "," if commas else "."
        before, _, after = text.rpartition(sep)
        if text.count(sep) > 1:
            if has_space:
                return _UNPARSEABLE
            decimal, thousands = None, sep
        elif has_space or len(after) != 3 or not before or len(before) > 3 or before[0] == "0":
            # A single separator that cannot be a thousands separator.
            decimal, thousands, proven = sep, (" " if has_space else None), sep
        elif minor == 0:
            decimal, thousands = None, sep
        elif decimal_hint == sep:
            decimal, thousands = sep, None
        elif decimal_hint is not None:
            decimal, thousands = None, sep
        else:
            return ParsedAmount(None, FlagCode.NUMBER_FORMAT_AMBIGUOUS)
    else:
        decimal, thousands = None, (" " if has_space else None)

    integer, _, fraction = text.partition(decimal) if decimal else (text, "", "")
    if fraction and not fraction.isdigit():
        return _UNPARSEABLE
    if thousands:
        groups = integer.split(thousands)
        if not _valid_grouping(groups, thousands):
            return _UNPARSEABLE
        integer = "".join(groups)
    if not integer and not fraction:
        return _UNPARSEABLE
    if integer and not integer.isdigit():
        return _UNPARSEABLE

    value = Decimal(f"{integer or '0'}.{fraction}" if fraction else integer)
    return ParsedAmount(-value if negative else value, decimal_separator=proven)


def detect_decimal_separator(raws: list[str | None]) -> DecimalSeparator | None:
    """The decimal separator proven by the document's unambiguous numbers, if consistent."""
    seen = {p.decimal_separator for raw in raws if (p := parse_amount(raw)).decimal_separator}
    return seen.pop() if len(seen) == 1 else None


# ------------------------------------------------------------------ dates


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    code: FlagCode | None = None
    # Set only when this string alone proves the day/month order (e.g. 25/03/2026).
    order: DateOrder | None = None


_MONTH_NAMES = [
    ("jan", "january"),
    ("feb", "february"),
    ("mar", "march"),
    ("apr", "april"),
    ("may",),
    ("jun", "june"),
    ("jul", "july"),
    ("aug", "august"),
    ("sep", "sept", "september"),
    ("oct", "october"),
    ("nov", "november"),
    ("dec", "december"),
]
_MONTHS = {name: number for number, names in enumerate(_MONTH_NAMES, 1) for name in names}

_ISO_DATE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
_NUMERIC_DATE = re.compile(r"(\d{1,2})([-/.])(\d{1,2})\2(\d{4}|\d{2})")
_DAY_FIRST = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]+)\.?,?[\s-]+(\d{4})", re.I)
_MONTH_FIRST = re.compile(r"([A-Za-z]+)\.?[\s-]+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)


def _build_date(year: int, month: int | None, day: int, order: DateOrder | None = None):
    if month is None:
        return ParsedDate(None, FlagCode.DATE_UNPARSEABLE)
    try:
        return ParsedDate(date(year, month, day), order=order)
    except ValueError:
        return ParsedDate(None, FlagCode.DATE_UNPARSEABLE)


def parse_date(raw: str | None, order_hint: DateOrder | None = None) -> ParsedDate:
    """Parse ISO, DD/MM/YYYY, MM/DD/YYYY, DD.MM.YYYY, "3 April 2026", "Apr 3, 2026".

    Dotted numeric dates (03.04.2026) follow the European day-first convention.
    Month names are English only.
    """
    text = clean_text(raw)
    if text is None:
        return ParsedDate(None)

    if match := _ISO_DATE.fullmatch(text):
        year, month, day = (int(part) for part in match.groups())
        return _build_date(year, month, day)

    if match := _NUMERIC_DATE.fullmatch(text):
        first, separator, second, year_text = match.groups()
        a, b = int(first), int(second)
        year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
        proven: DateOrder | None = None
        if separator == ".":
            order: DateOrder | None = "DMY"
        elif a > 12:
            order = proven = "DMY"
        elif b > 12:
            order = proven = "MDY"
        elif a == b:
            order = "DMY"  # both readings give the same date
        else:
            order = order_hint
        if order is None:
            return ParsedDate(None, FlagCode.DATE_AMBIGUOUS)
        day, month = (a, b) if order == "DMY" else (b, a)
        return _build_date(year, month, day, proven)

    if match := _DAY_FIRST.fullmatch(text):
        day, month_name, year = match.groups()
        return _build_date(int(year), _MONTHS.get(month_name.lower()), int(day))

    if match := _MONTH_FIRST.fullmatch(text):
        month_name, day, year = match.groups()
        return _build_date(int(year), _MONTHS.get(month_name.lower()), int(day))

    return ParsedDate(None, FlagCode.DATE_UNPARSEABLE)


def detect_date_order(raws: list[str | None]) -> DateOrder | None:
    """The day/month order proven by the document's unambiguous dates, if consistent."""
    seen = {p.order for raw in raws if (p := parse_date(raw)).order}
    return seen.pop() if len(seen) == 1 else None


# ------------------------------------------------------------- currencies


@dataclass(frozen=True)
class ParsedCurrency:
    value: str | None
    code: FlagCode | None = None


def parse_currency(raw: str | None) -> ParsedCurrency:
    """Parse "EUR", "usd", "€", "US$", "Rs.", "Euro (EUR)". "$" alone is ambiguous."""
    text = clean_text(raw)
    if text is None:
        return ParsedCurrency(None)

    key = text.upper().replace(" ", "")
    if key in ISO_4217:
        return ParsedCurrency(key)
    if key in _CURRENCY_SYMBOLS:
        return ParsedCurrency(_CURRENCY_SYMBOLS[key])
    if key in _AMBIGUOUS_SYMBOLS:
        return ParsedCurrency(None, FlagCode.CURRENCY_AMBIGUOUS)

    codes = {c for c in re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", text.upper()) if c in ISO_4217}
    codes |= {code for symbol, code in _SINGLE_CHAR_SYMBOLS.items() if symbol in text}
    if len(codes) == 1:
        return ParsedCurrency(codes.pop())
    return ParsedCurrency(None, FlagCode.CURRENCY_UNKNOWN)


def currency_from_amounts(raws: list[str | None]) -> ParsedCurrency | None:
    """Currency implied by symbols/codes printed next to amounts ("€ 12,00", "USD 5")."""
    found: set[str] = set()
    ambiguous = False
    for raw in raws:
        text = clean_text(raw)
        if text is None:
            continue
        marker = re.sub(r"[\d.,'’()+\-−\s]", "", text)
        if not marker:
            continue
        parsed = parse_currency(marker)
        if parsed.value:
            found.add(parsed.value)
        elif parsed.code == FlagCode.CURRENCY_AMBIGUOUS:
            ambiguous = True
    if len(found) == 1:
        return ParsedCurrency(found.pop())
    if found or ambiguous:
        return ParsedCurrency(None, FlagCode.CURRENCY_AMBIGUOUS)
    return None
