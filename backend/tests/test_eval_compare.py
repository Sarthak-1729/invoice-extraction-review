"""METRICS.md comparison rules, checked on the dev truth files."""

import copy
import json

import pytest

from app.eval_compare import (
    CONFIGURATION_ERROR,
    INFRASTRUCTURE_FAILURE,
    MODEL_FAILURE,
    compare_document,
    failure_class,
    match_lines,
    values_equal,
)
from app.schemas.invoice import RawExtraction
from app.testset_guard import REPO_ROOT
from app.validation.checks import check_invoice

DEV_TRUTH = REPO_ROOT / "eval" / "datasets" / "dev" / "truth"


def truth(doc_id):
    return json.loads((DEV_TRUTH / f"{doc_id}.json").read_text(encoding="utf-8"))


def perfect(t):
    raw = {k: f["printed"] for k, f in t["fields"].items()}
    raw["line_items"] = [{k: f["printed"] for k, f in line.items()} for line in t["line_items"]]
    return raw


def score(t, raw, **kwargs):
    checked = check_invoice(RawExtraction.model_validate(raw))
    flags = [f.model_dump(mode="json") for f in checked.flags]
    return compare_document(t, raw, checked.invoice.model_dump(mode="json"), flags, **kwargs)


@pytest.mark.parametrize("doc_id", [f"dev-{n:02d}" for n in range(1, 11)])
def test_perfect_extraction_scores_fully(doc_id):
    t = truth(doc_id)
    c = score(t, perfect(t))
    assert c.count("layer1") == len(c.fields)  # every printed string copied
    # Layer 2: everything accurate except ambiguity the document itself has.
    assert all(f.layer2 or f.outcome == "ambiguous" for f in c.fields)
    assert not c.missing_lines and not c.extra_lines
    assert len(c.matched_lines) == c.truth_lines
    if not t["arithmetic_consistent"]:
        assert c.expected_arithmetic_flag in c.flag_codes
    else:
        assert not c.arithmetic_flag_fired


def test_dollar_only_currency_is_ambiguous_not_wrong():
    t = truth("dev-03")
    c = score(t, perfect(t))
    currency = next(f for f in c.fields if f.path == "currency")
    assert currency.layer1 and currency.outcome == "ambiguous"


def test_wrong_missing_and_hallucinated_outcomes():
    t = truth("dev-01")
    raw = perfect(t)
    raw["total"] = "$35,292.96"  # wrong
    raw["invoice_number"] = None  # missing
    t2 = copy.deepcopy(t)
    t2["fields"]["bill_to_name"] = {"value": None, "printed": None}  # truth has no customer
    c = score(t2, raw)
    outcomes = {f.path: f.outcome for f in c.fields}
    assert outcomes["total"] == "wrong"
    assert outcomes["invoice_number"] == "missing"
    assert outcomes["bill_to_name"] == "hallucinated"


def test_layer1_and_layer2_can_disagree():
    """Copied differently but normalizes to the same value: layer 1 no, layer 2 yes."""
    t = truth("dev-01")
    raw = perfect(t)
    raw["total"] = "35292.69"
    total = next(f for f in score(t, raw).fields if f.path == "total")
    assert (total.layer1, total.outcome) == (False, "correct")


def test_currency_exception_uses_a_marker_printed_in_the_document():
    t = truth("dev-04")  # printed currency "€"
    t["fields"]["currency"]["printed"] = "EUR"
    raw = perfect(truth("dev-04"))  # model returns "€"
    with_text = score(t, raw, document_text="Total 11.693,81 €")
    currency = next(f for f in with_text.fields if f.path == "currency")
    assert currency.layer1 and currency.note == "layer 1 currency exception"
    assert with_text.currency_exceptions == 1
    without = next(
        f for f in score(t, raw, document_text="no marker").fields if f.path == "currency"
    )
    assert not without.layer1


def test_line_matching_exact_then_fuzzy_then_unmatched():
    truth_lines = [{"description": d} for d in ("Monitor arm", "Wireless keyboard", "Cable kit")]
    predicted = [{"description": d} for d in ("wireless  KEYBOARD", "Monitr arm", "Coffee")]
    assert match_lines(truth_lines, predicted) == [(0, 1), (1, 0)]


def test_reordered_and_extra_lines():
    t = truth("dev-01")
    raw = perfect(t)
    raw["line_items"] = list(reversed(raw["line_items"])) + [
        {"description": "Invented item", "quantity": "1", "unit_price": "$1.00", "amount": "$1.00"}
    ]
    del raw["line_items"][0]  # drop the last truth line
    c = score(t, raw)
    assert len(c.matched_lines) == 5 and c.missing_lines == [5] and c.extra_lines == [5]
    assert all(f.layer2 for f in c.fields if f.path.startswith("line_items"))


def test_model_failure_makes_every_field_missing():
    t = truth("dev-01")
    c = compare_document(t, None, None, [], error_code="SCHEMA_VALIDATION_FAILED")
    assert c.failure == MODEL_FAILURE
    assert {f.outcome for f in c.fields} == {"missing"}
    assert c.missing_lines == list(range(6))


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (None, None),
        ("SCHEMA_VALIDATION_FAILED", MODEL_FAILURE),
        ("LLM_OUTPUT_INCOMPLETE", MODEL_FAILURE),
        ("LLM_UNAVAILABLE", INFRASTRUCTURE_FAILURE),
        ("LLM_RATE_LIMITED", INFRASTRUCTURE_FAILURE),
        ("LLM_TIMEOUT", INFRASTRUCTURE_FAILURE),
        ("LLM_ERROR", INFRASTRUCTURE_FAILURE),
        ("SOMETHING_NEW", INFRASTRUCTURE_FAILURE),
        ("LLM_AUTH_FAILED", CONFIGURATION_ERROR),
        ("LLM_BAD_REQUEST", CONFIGURATION_ERROR),
        ("LLM_NOT_CONFIGURED", CONFIGURATION_ERROR),
    ],
)
def test_failure_classes_follow_metrics_2a(code, expected):
    assert failure_class(code) == expected


@pytest.mark.parametrize(
    ("name", "a", "b", "equal"),
    [
        ("total", "1234.5", "1234.50", True),
        ("invoice_number", "INV 1042", "INV1042", True),
        ("invoice_number", "inv1042", "INV1042", False),
        ("vendor_name", "ACME  ltd", "Acme Ltd", True),
        ("invoice_date", "2026-03-25", "2026-03-25", True),
        ("currency", "EUR", "USD", False),
        ("total", "not a number", "1", False),
    ],
)
def test_layer2_equality_rules(name, a, b, equal):
    assert values_equal(name, a, b) is equal
