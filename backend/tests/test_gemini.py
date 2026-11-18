"""Gemini provider without network: error mapping, request shape, pacing."""

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx2
import pytest

from app.llm import LLMError, LLMErrorCode
from app.llm.gemini import REDACTED, GeminiProvider, map_provider_error, parse_retry_after
from app.llm.pacing import Pacer
from app.prompt import load_prompt


class FakeStatusError(Exception):
    """Shaped like the SDK's status errors: status_code, response.headers, body."""

    def __init__(self, status, headers=None, body=""):
        super().__init__(f"HTTP {status}")
        self.status_code = status
        self.response = SimpleNamespace(status_code=status, headers=httpx2.Headers(headers or {}))
        self.body = body


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


@pytest.mark.parametrize(
    ("error", "code", "retry_after"),
    [
        (FakeStatusError(429, {"Retry-After": "7"}), LLMErrorCode.RATE_LIMITED, 7.0),
        (
            FakeStatusError(429, body='{"details": [{"retryDelay": "12s"}]}'),
            LLMErrorCode.RATE_LIMITED,
            12.0,
        ),
        (FakeStatusError(429), LLMErrorCode.RATE_LIMITED, None),
        (FakeStatusError(503, {"retry-after": "3"}), LLMErrorCode.UNAVAILABLE, 3.0),
        (FakeStatusError(500), LLMErrorCode.UNAVAILABLE, None),
        (FakeStatusError(504), LLMErrorCode.TIMEOUT, None),
        (FakeStatusError(401), LLMErrorCode.AUTH_FAILED, None),
        (FakeStatusError(403), LLMErrorCode.AUTH_FAILED, None),
        (FakeStatusError(400), LLMErrorCode.BAD_REQUEST, None),
        (FakeStatusError(404), LLMErrorCode.BAD_REQUEST, None),
        # The SDK raises httpx2 errors (it prefers httpx2 when installed).
        (httpx2.ReadTimeout("slow"), LLMErrorCode.TIMEOUT, None),
        (httpx2.ConnectTimeout("slow"), LLMErrorCode.TIMEOUT, None),
        (APITimeoutError("slow"), LLMErrorCode.TIMEOUT, None),
        (APIConnectionError("dns"), LLMErrorCode.UNAVAILABLE, None),
        (httpx2.ConnectError("refused"), LLMErrorCode.UNAVAILABLE, None),
        (httpx2.RemoteProtocolError("closed"), LLMErrorCode.UNAVAILABLE, None),
        (ValueError("odd"), LLMErrorCode.ERROR, None),
    ],
)
def test_provider_errors_map_to_codes(error, code, retry_after):
    mapped = map_provider_error(error)
    assert (mapped.code, mapped.retry_after) == (code, retry_after)


def test_retryable_codes():
    assert map_provider_error(FakeStatusError(429)).retryable
    assert map_provider_error(FakeStatusError(503)).retryable
    assert not map_provider_error(FakeStatusError(401)).retryable
    assert not map_provider_error(FakeStatusError(400)).retryable


FAKE_KEY = "AIza" + "x" * 35  # shaped like a Gemini key; not a real one


def test_full_provider_message_is_kept():
    long_message = "The specified schema produces a constraint that has too many states. " * 20
    error = FakeStatusError(400)
    error.args = (long_message,)
    mapped = map_provider_error(error)
    assert long_message.strip() in mapped.message  # no truncation


def test_body_is_appended_when_it_adds_detail():
    mapped = map_provider_error(FakeStatusError(400, body='{"error": {"code": "invalid_request"}}'))
    assert "invalid_request" in mapped.message


@pytest.mark.parametrize(
    "text",
    [
        f"bad key {FAKE_KEY}",
        "https://example.test/v1/models?key=abc123def&alt=json",
        "configured key: my-custom-secret-value",
    ],
)
def test_keys_are_redacted_from_messages(text):
    error = FakeStatusError(401, body=text)
    mapped = map_provider_error(error, secrets=("my-custom-secret-value",))
    for secret in (FAKE_KEY, "abc123def", "my-custom-secret-value"):
        assert secret not in mapped.message
    assert REDACTED in mapped.message


def test_provider_redacts_its_own_key():
    provider, _ = _provider(
        error=FakeStatusError(400, body="echo: test-key-not-real"), min_interval_seconds=0
    )
    with pytest.raises(LLMError) as info:
        provider.generate("s", "u", {})
    assert "test-key-not-real" not in info.value.message


def test_parse_retry_after_http_date():
    now = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Wed, 04 Nov 2026 12:00:30 GMT", now) == 30.0
    assert parse_retry_after("garbage") is None
    assert parse_retry_after(None) is None


@pytest.mark.parametrize(("key", "model"), [(None, "m"), ("", "m"), ("k", None), ("k", "")])
def test_missing_configuration(key, model):
    with pytest.raises(LLMError) as info:
        GeminiProvider(key, model)
    assert info.value.code == LLMErrorCode.NOT_CONFIGURED


class StubInteractions:
    def __init__(self, result=None, error=None):
        self.calls, self.result, self.error = [], result, error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def _provider(result=None, error=None, **kwargs):
    provider = GeminiProvider("test-key-not-real", "gemini-3.5-flash-lite", **kwargs)
    stub = StubInteractions(result, error)
    provider._client = SimpleNamespace(interactions=stub)  # no network
    return provider, stub


def test_request_shape():
    done = SimpleNamespace(status="completed", output_text='{"total": "1"}', usage=None)
    provider, stub = _provider(done, thinking_level="low", min_interval_seconds=0)
    prompt = load_prompt()
    response = provider.generate(prompt.system, "user text", prompt.schema)
    assert response.text == '{"total": "1"}'
    call = stub.calls[0]
    assert call["model"] == "gemini-3.5-flash-lite"
    assert call["system_instruction"] == prompt.system
    assert call["input"] == "user text"
    assert call["store"] is False
    assert call["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": prompt.schema,
    }
    assert call["generation_config"] == {"max_output_tokens": 16384, "thinking_level": "low"}


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(status="incomplete", output_text='{"a"', usage=None),
        SimpleNamespace(status="completed", output_text="", usage=None),
    ],
)
def test_incomplete_output(result):
    provider, _ = _provider(result, min_interval_seconds=0)
    with pytest.raises(LLMError) as info:
        provider.generate("s", "u", {})
    assert info.value.code == LLMErrorCode.INCOMPLETE


def test_sdk_errors_are_mapped():
    provider, _ = _provider(
        error=FakeStatusError(429, {"Retry-After": "5"}), min_interval_seconds=0
    )
    with pytest.raises(LLMError) as info:
        provider.generate("s", "u", {})
    assert (info.value.code, info.value.retry_after) == (LLMErrorCode.RATE_LIMITED, 5.0)


def test_pacer_spaces_requests():
    now = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    pacer = Pacer(6.0, clock=lambda: now[0], sleep=sleep)
    pacer.wait()  # first request: no wait
    now[0] += 2.0
    pacer.wait()  # 2 s later: wait 4 s
    now[0] += 10.0
    pacer.wait()  # 10 s later: no wait
    assert sleeps == [4.0]


def test_plain_httpx_errors_still_map_when_httpx_is_installed():
    httpx = pytest.importorskip("httpx")  # optional; older google-genai versions raise these
    assert map_provider_error(httpx.ConnectError("refused")).code == LLMErrorCode.UNAVAILABLE
    assert map_provider_error(httpx.ReadTimeout("slow")).code == LLMErrorCode.TIMEOUT
