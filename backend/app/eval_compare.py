"""Compare one extraction with its truth file, following docs/METRICS.md.

Used by ``app.dev_check`` now and by the Phase 7 evaluation later. It scores
fields only; aggregation into reported metrics happens elsewhere.
"""

import difflib
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.validation.formats import parse_currency

METRICS_VERSION = "1.1"

HEADER_FIELDS = (
    "invoice_number",
    "vendor_name",
    "bill_to_name",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax",
    "total",
)
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")
NUMERIC_FIELDS = {"subtotal", "tax", "total", "quantity", "unit_price", "amount"}
TEXT_FIELDS = {"vendor_name", "bill_to_name", "description"}
FUZZY_MATCH_MIN = 0.6
ACCURATE = {"correct", "correct_absent"}

# Section 2a: failure classes by error code.
MODEL_FAILURE = "model_failure"
INFRASTRUCTURE_FAILURE = "infrastructure_failure"
CONFIGURATION_ERROR = "configuration_error"
_FAILURE_CLASSES = {
    "SCHEMA_VALIDATION_FAILED": MODEL_FAILURE,
    "LLM_OUTPUT_INCOMPLETE": MODEL_FAILURE,
    "LLM_UNAVAILABLE": INFRASTRUCTURE_FAILURE,
    "LLM_RATE_LIMITED": INFRASTRUCTURE_FAILURE,
    "LLM_TIMEOUT": INFRASTRUCTURE_FAILURE,
    "LLM_ERROR": INFRASTRUCTURE_FAILURE,
    "LLM_AUTH_FAILED": CONFIGURATION_ERROR,
    "LLM_NOT_CONFIGURED": CONFIGURATION_ERROR,
    "LLM_BAD_REQUEST": CONFIGURATION_ERROR,
}

# Symbols the normalizer calls ambiguous, and the codes they can stand for
# (layer 1 currency exception, METRICS section 3).
_AMBIGUOUS_SYMBOL_CODES = {
    "$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN"},
    "¥": {"JPY", "CNY"},
    "KR": {"SEK", "NOK", "DKK", "ISK"},
    "KR.": {"SEK", "NOK", "DKK", "ISK"},
}

ARITHMETIC_CODES = {"LINE_AMOUNT_MISMATCH", "SUBTOTAL_MISMATCH", "TOTAL_MISMATCH"}
_EXPECTED_ARITHMETIC = {
    "arith_error:line": "LINE_AMOUNT_MISMATCH",
    "arith_error:subtotal": "SUBTOTAL_MISMATCH",
    "arith_error:total": "TOTAL_MISMATCH",
}


def failure_class(error_code: str | None) -> str | None:
    """None for success; unknown codes count as infrastructure (retried)."""
    if error_code is None:
        return None
    return _FAILURE_CLASSES.get(error_code, INFRASTRUCTURE_FAILURE)


def layer1_text(value: str | None) -> str | None:
    """NFKC, whitespace collapsed, trimmed; otherwise exact."""
    if value is None:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _fold(value: str) -> str:
    return layer1_text(value).casefold()


def values_equal(name: str, predicted: Any, truth: Any) -> bool:
    """Layer 2 equality rules (METRICS section 4); both values non-null."""
    if name in NUMERIC_FIELDS:
        try:
            return Decimal(str(predicted)) == Decimal(str(truth))
        except InvalidOperation:
            return False
    if name == "invoice_number":
        squash = lambda v: "".join(unicodedata.normalize("NFKC", str(v)).split())  # noqa: E731
        return squash(predicted) == squash(truth)
    if name in TEXT_FIELDS:
        return _fold(str(predicted)) == _fold(str(truth))
    return str(predicted) == str(truth)  # ISO dates, ISO currency codes


@dataclass
class FieldResult:
    path: str
    raw: Any
    printed: Any
    normalized: Any
    value: Any
    layer1: bool
    outcome: str  # layer 2 outcome
    note: str = ""

    @property
    def layer2(self) -> bool:
        return self.outcome in ACCURATE

    @property
    def differs(self) -> bool:
        return not self.layer1 or not self.layer2


@dataclass
class DocComparison:
    doc_id: str
    failure: str | None = None
    fields: list[FieldResult] = field(default_factory=list)
    matched_lines: list[tuple[int, int]] = field(default_factory=list)  # (truth, predicted)
    missing_lines: list[int] = field(default_factory=list)  # truth indices
    extra_lines: list[int] = field(default_factory=list)  # predicted indices
    truth_lines: int = 0
    predicted_lines: int = 0
    flag_codes: list[str] = field(default_factory=list)
    arithmetic_consistent: bool = True
    expected_arithmetic_flag: str | None = None
    arithmetic_flag_fired: bool = False
    currency_exceptions: int = 0

    def count(self, attribute: str) -> int:
        return sum(1 for f in self.fields if getattr(f, attribute))

    @property
    def ambiguous(self) -> int:
        return sum(1 for f in self.fields if f.outcome == "ambiguous")


def _outcome(name: str, predicted: Any, truth: Any, ambiguous: bool) -> str:
    if truth is None:
        return "correct_absent" if predicted is None else "hallucinated"
    if predicted is None:
        return "ambiguous" if ambiguous else "missing"
    return "correct" if values_equal(name, predicted, truth) else "wrong"


def _currency_exception(raw: str | None, truth_code: str | None, text: str | None) -> bool:
    """Raw currency marker printed elsewhere in the document, same ISO code."""
    if not raw or not truth_code or not text:
        return False
    marker = layer1_text(raw)
    if marker not in layer1_text(text):
        return False
    parsed = parse_currency(marker)
    if parsed.value:
        return parsed.value == truth_code
    return truth_code in _AMBIGUOUS_SYMBOL_CODES.get(marker.upper(), set())


def _description_key(line: dict[str, Any]) -> str:
    text = line.get("description")
    return _fold(text) if text else ""


def match_lines(
    truth_lines: list[dict[str, Any]], predicted_lines: list[dict[str, Any]]
) -> list[tuple[int, int]]:
    """METRICS section 5: exact normalized descriptions first, in document order;
    then greedy difflib ratio >= 0.6, highest first, ties by truth then predicted
    order. Inputs are layer 2 lines (truth values, normalized predictions)."""
    truth_keys = [_description_key(line) for line in truth_lines]
    predicted_keys = [_description_key(line) for line in predicted_lines]
    used_truth: set[int] = set()
    used_predicted: set[int] = set()
    pairs: list[tuple[int, int]] = []

    for t, key in enumerate(truth_keys):
        for p, candidate in enumerate(predicted_keys):
            if p not in used_predicted and key and key == candidate:
                pairs.append((t, p))
                used_truth.add(t)
                used_predicted.add(p)
                break

    scored = [
        (difflib.SequenceMatcher(None, truth_keys[t], predicted_keys[p]).ratio(), t, p)
        for t in range(len(truth_keys))
        if t not in used_truth
        for p in range(len(predicted_keys))
        if p not in used_predicted
    ]
    for ratio, t, p in sorted(scored, key=lambda s: (-s[0], s[1], s[2])):
        if ratio >= FUZZY_MATCH_MIN and t not in used_truth and p not in used_predicted:
            pairs.append((t, p))
            used_truth.add(t)
            used_predicted.add(p)
    return sorted(pairs)


def compare_document(
    truth: dict[str, Any],
    raw: dict[str, Any] | None,
    normalized: dict[str, Any] | None,
    flags: list[dict[str, Any]],
    *,
    error_code: str | None = None,
    document_text: str | None = None,
) -> DocComparison:
    truth_fields = truth["fields"]
    truth_lines = truth["line_items"]
    features = truth.get("features", [])
    result = DocComparison(
        doc_id=truth["doc_id"],
        failure=failure_class(error_code),
        truth_lines=len(truth_lines),
        arithmetic_consistent=truth.get("arithmetic_consistent", True),
        expected_arithmetic_flag=next(
            (code for feature, code in _EXPECTED_ARITHMETIC.items() if feature in features), None
        ),
    )

    if raw is None or normalized is None:
        # Model failure (or no output): every field missing, every line unmatched.
        for name in HEADER_FIELDS:
            f = truth_fields[name]
            result.fields.append(
                FieldResult(name, None, f["printed"], None, f["value"], False, "missing")
            )
        result.missing_lines = list(range(len(truth_lines)))
        return result

    result.flag_codes = sorted({flag["code"] for flag in flags})
    result.arithmetic_flag_fired = bool(set(result.flag_codes) & ARITHMETIC_CODES)
    ambiguous_paths = {flag["field_path"] for flag in flags if flag["code"].endswith("_AMBIGUOUS")}

    for name in HEADER_FIELDS:
        f = truth_fields[name]
        layer1 = layer1_text(raw.get(name)) == layer1_text(f["printed"])
        note = ""
        if (
            not layer1
            and name == "currency"
            and _currency_exception(raw.get(name), f["value"], document_text)
        ):
            layer1, note = True, "layer 1 currency exception"
            result.currency_exceptions += 1
        outcome = _outcome(name, normalized.get(name), f["value"], name in ambiguous_paths)
        result.fields.append(
            FieldResult(
                name,
                raw.get(name),
                f["printed"],
                normalized.get(name),
                f["value"],
                layer1,
                outcome,
                note,
            )
        )

    raw_lines = raw.get("line_items") or []
    predicted_lines = normalized.get("line_items") or []
    result.predicted_lines = len(predicted_lines)
    truth_values = [{k: line[k]["value"] for k in LINE_FIELDS} for line in truth_lines]
    result.matched_lines = match_lines(truth_values, predicted_lines)
    matched_truth = {t for t, _ in result.matched_lines}
    matched_predicted = {p for _, p in result.matched_lines}
    result.missing_lines = [t for t in range(len(truth_lines)) if t not in matched_truth]
    result.extra_lines = [p for p in range(len(predicted_lines)) if p not in matched_predicted]

    for t, p in result.matched_lines:
        for name in LINE_FIELDS:
            f = truth_lines[t][name]
            raw_value = raw_lines[p].get(name) if p < len(raw_lines) else None
            predicted = predicted_lines[p].get(name)
            ambiguous = f"line_items[{p}].{name}" in ambiguous_paths
            result.fields.append(
                FieldResult(
                    f"line_items[{t}].{name}",
                    raw_value,
                    f["printed"],
                    predicted,
                    f["value"],
                    layer1_text(raw_value) == layer1_text(f["printed"]),
                    _outcome(name, predicted, f["value"], ambiguous),
                    "" if p == t else f"matched predicted line {p}",
                )
            )
    return result
