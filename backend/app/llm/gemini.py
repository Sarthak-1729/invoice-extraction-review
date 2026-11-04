"""Gemini provider (google-genai SDK, Interactions API, structured output).

Checked against the official docs on 2026-11-04: ``client.interactions.create``
with ``response_format={"type": "text", "mime_type": "application/json",
"schema": ...}``, reading ``interaction.output_text``. The SDK's own retries
are turned off so that retries and pacing are decided in one place
(``app.extraction``). Requests are sent with ``store=False``.
"""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.llm.base import LLMError, LLMErrorCode, LLMResponse
from app.llm.pacing import Pacer

_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        *,
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 16384,
        thinking_level: str | None = None,
        min_interval_seconds: float = 6.0,
    ) -> None:
        if not api_key:
            raise LLMError(LLMErrorCode.NOT_CONFIGURED, "GEMINI_API_KEY is not set.")
        if not model:
            raise LLMError(LLMErrorCode.NOT_CONFIGURED, "GEMINI_MODEL is not set.")
        from google import genai  # imported here so tests never need the SDK
        from google.genai import types

        self.model = model
        self._api_key = api_key  # kept only to redact it from error messages
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level
        self.pacer = Pacer(min_interval_seconds)
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=0),
            ),
        )

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        generation_config: dict[str, Any] = {"max_output_tokens": self.max_output_tokens}
        if self.thinking_level:
            generation_config["thinking_level"] = self.thinking_level
        self.pacer.wait()
        try:
            interaction = self._client.interactions.create(
                model=self.model,
                system_instruction=system,
                input=user,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
                generation_config=generation_config,
                store=False,
            )
        except Exception as error:  # SDK error classes are mapped by status code
            raise map_provider_error(error, secrets=(self._api_key,)) from error

        status = getattr(interaction, "status", None)
        if status not in (None, "completed"):
            raise LLMError(LLMErrorCode.INCOMPLETE, f"Interaction ended with status {status!r}.")
        text = getattr(interaction, "output_text", None)
        if not text:
            raise LLMError(LLMErrorCode.INCOMPLETE, "The model returned no text.")
        usage = getattr(interaction, "usage", None)
        usage_dict = usage.model_dump(exclude_none=True) if hasattr(usage, "model_dump") else {}
        return LLMResponse(text=text, usage=usage_dict)


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Retry-After header: seconds, or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


def _status_code(error: Exception) -> int | None:
    for candidate in (
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
        getattr(error, "code", None),
    ):
        if isinstance(candidate, int):
            return candidate
    return None


def _retry_after(error: Exception) -> float | None:
    """From the Retry-After header, else a google.rpc.RetryInfo delay in the body.
    The docs promise neither, so both are optional."""
    response = getattr(error, "response", None) or getattr(error, "raw_response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None)
    if headers is not None:
        seconds = parse_retry_after(headers.get("retry-after"))
        if seconds is not None:
            return seconds
    match = _RETRY_DELAY.search(str(getattr(error, "body", "") or ""))
    return float(match.group(1)) if match else None


_API_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")
_KEY_PARAM = re.compile(r"(key=)[^&\s\"']+", re.IGNORECASE)
REDACTED = "[REDACTED]"


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove API keys from text that will be printed or stored."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _API_KEY.sub(REDACTED, text)
    return _KEY_PARAM.sub(rf"\1{REDACTED}", text)


def _full_detail(error: Exception) -> str:
    """The provider's complete message (no truncation), plus the body if it adds anything."""
    message = str(error).strip()
    body = getattr(error, "body", None)
    body_text = body if isinstance(body, str) else (repr(body) if body else "")
    if body_text and body_text.strip() not in message:
        message = f"{message} | body: {body_text.strip()}" if message else body_text.strip()
    return message


def map_provider_error(error: Exception, secrets: tuple[str, ...] = ()) -> LLMError:
    name = type(error).__name__
    status = _status_code(error)
    detail = redact(_full_detail(error), secrets)
    if isinstance(error, httpx.TimeoutException) or "Timeout" in name or status in (408, 504):
        return LLMError(LLMErrorCode.TIMEOUT, f"Request timed out. {detail}".strip())
    if status == 429:
        return LLMError(
            LLMErrorCode.RATE_LIMITED,
            f"Rate limit or quota hit (429). {detail}",
            _retry_after(error),
        )
    if status in (401, 403):
        return LLMError(
            LLMErrorCode.AUTH_FAILED,
            f"Authentication failed ({status}); check GEMINI_API_KEY. {detail}".strip(),
        )
    if status is not None and 500 <= status < 600:
        return LLMError(
            LLMErrorCode.UNAVAILABLE,
            f"Service unavailable ({status}). {detail}",
            _retry_after(error),
        )
    if status is not None and 400 <= status < 500:
        return LLMError(LLMErrorCode.BAD_REQUEST, f"Request rejected ({status}). {detail}")
    if isinstance(error, httpx.TransportError) or "Connection" in name:
        return LLMError(LLMErrorCode.UNAVAILABLE, f"Could not reach the API. {detail}")
    return LLMError(LLMErrorCode.ERROR, f"{name}: {detail}")
