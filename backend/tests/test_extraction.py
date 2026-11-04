"""Extraction retries and validation, with the fake provider only."""

import json

from app.extraction import SCHEMA_VALIDATION_FAILED, extract_raw
from app.llm import FakeProvider, LLMError, LLMErrorCode
from app.prompt import load_prompt

GOOD = json.dumps(
    {
        "invoice_number": "INV-1",
        "vendor_name": "Acme Ltd",
        "bill_to_name": None,
        "invoice_date": "2026-03-25",
        "due_date": None,
        "currency": "EUR",
        "subtotal": "10,00 €",
        "tax": None,
        "total": "10,00 €",
        "line_items": [
            {"description": "Widget", "quantity": "1", "unit_price": "10,00", "amount": "10,00"}
        ],
    }
)


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def run(steps, **kwargs):
    provider = FakeProvider(steps)
    sleeps = Sleeps()
    result = extract_raw("Invoice text", provider, sleep=sleeps, **kwargs)
    return result, provider, sleeps


def test_valid_output_is_parsed_in_one_call():
    result, provider, sleeps = run([GOOD])
    assert result.ok and result.raw.invoice_number == "INV-1"
    assert len(provider.calls) == 1 and sleeps == []
    call = provider.calls[0]
    assert call["system"] == load_prompt().system
    assert "<document_text>\nInvoice text\n</document_text>" in call["user"]
    assert call["schema"] == load_prompt().schema


def test_one_retry_on_schema_failure_then_success():
    result, provider, _ = run(["not json", GOOD])
    assert result.ok
    assert [a["outcome"] for a in result.attempts] == [SCHEMA_VALIDATION_FAILED, "ok"]
    assert len(provider.calls) == 2


def test_two_schema_failures_fail_the_extraction():
    extra_key = json.dumps({"invoice_number": "1", "confidence": 0.99})
    result, provider, _ = run(["{oops", extra_key])
    assert not result.ok
    assert result.error_code == SCHEMA_VALIDATION_FAILED
    assert "confidence" in result.error_message
    assert len(provider.calls) == 2


def test_wrong_types_and_oversized_values_fail_validation():
    too_long = json.dumps({"invoice_number": "x" * 501})
    wrong_type = json.dumps({"line_items": "not a list"})
    result, _, _ = run([too_long, wrong_type])
    assert result.error_code == SCHEMA_VALIDATION_FAILED


def test_rate_limit_waits_for_retry_after():
    result, provider, sleeps = run([LLMError(LLMErrorCode.RATE_LIMITED, "429", 7.0), GOOD])
    assert result.ok and sleeps == [7.0] and len(provider.calls) == 2


def test_unavailable_uses_exponential_backoff_then_gives_up():
    error = LLMError(LLMErrorCode.UNAVAILABLE, "503")
    result, provider, sleeps = run([error], transient_retries=3)
    assert sleeps == [2.0, 4.0, 8.0]
    assert len(provider.calls) == 4
    assert result.error_code == LLMErrorCode.UNAVAILABLE


def test_timeouts_are_retried():
    result, _, sleeps = run([LLMError(LLMErrorCode.TIMEOUT, "slow"), GOOD])
    assert result.ok and sleeps == [2.0]


def test_long_retry_after_fails_without_blocking():
    error = LLMError(LLMErrorCode.RATE_LIMITED, "daily quota", retry_after=3600)
    result, provider, sleeps = run([error], max_backoff=60)
    assert sleeps == [] and len(provider.calls) == 1
    assert result.error_code == LLMErrorCode.RATE_LIMITED and result.retry_after == 3600


def test_backoff_is_capped():
    error = LLMError(LLMErrorCode.UNAVAILABLE, "503")
    _, _, sleeps = run([error], transient_retries=5, max_backoff=10)
    assert sleeps == [2.0, 4.0, 8.0, 10.0, 10.0]


def test_non_retryable_errors_fail_immediately():
    for code in (LLMErrorCode.AUTH_FAILED, LLMErrorCode.BAD_REQUEST, LLMErrorCode.INCOMPLETE):
        result, provider, sleeps = run([LLMError(code, "no")])
        assert result.error_code == code and len(provider.calls) == 1 and sleeps == []


def test_model_confidence_fields_are_rejected_not_used():
    """The schema forbids extra keys, so a self-reported confidence never gets in."""
    with_confidence = json.loads(GOOD) | {"confidence": {"total": 0.99}}
    result, _, _ = run([json.dumps(with_confidence)] * 2)
    assert result.error_code == SCHEMA_VALIDATION_FAILED
