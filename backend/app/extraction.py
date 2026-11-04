"""Ask the provider for a raw extraction and validate it with Pydantic.

- Schema failure (not JSON, or not matching ``RawExtraction``): one retry, then
  the extraction fails with ``SCHEMA_VALIDATION_FAILED``.
- Transient provider errors (429, 503, timeouts): up to ``transient_retries``
  retries, waiting for Retry-After when the provider gives it, otherwise
  exponential backoff (2 s, 4 s, 8 s, ...). A Retry-After longer than
  ``max_backoff`` fails immediately instead of blocking (for example a daily
  quota).
- Any other provider error fails immediately with its error code.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.llm.base import LLMError, LLMProvider
from app.prompt import Prompt, load_prompt
from app.schemas.invoice import RawExtraction

SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
SCHEMA_ATTEMPTS = 2  # first try + one retry


@dataclass
class ExtractionResult:
    raw: RawExtraction | None
    error_code: str | None = None
    error_message: str | None = None
    retry_after: float | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    usage: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.raw is not None


def _summarize(error: ValidationError) -> str:
    problems = [
        f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in error.errors()
    ]
    shown = "; ".join(problems[:3])
    more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
    return f"Output did not match the schema: {shown}{more}"


def extract_raw(
    document_text: str,
    provider: LLMProvider,
    *,
    prompt: Prompt | None = None,
    transient_retries: int = 3,
    max_backoff: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> ExtractionResult:
    prompt = prompt or load_prompt()
    user = prompt.user_message(document_text)
    result = ExtractionResult(raw=None)
    schema_failures = 0
    transient_failures = 0

    while True:
        try:
            response = provider.generate(prompt.system, user, prompt.schema)
        except LLMError as error:
            result.attempts.append({"outcome": error.code, "retry_after": error.retry_after})
            too_long = error.retry_after is not None and error.retry_after > max_backoff
            if error.retryable and transient_failures < transient_retries and not too_long:
                delay = error.retry_after
                if delay is None:
                    delay = min(max_backoff, 2.0 * 2**transient_failures)
                transient_failures += 1
                sleep(delay)
                continue
            result.error_code, result.error_message = error.code, error.message
            result.retry_after = error.retry_after
            return result

        if response.usage:
            result.usage.append(response.usage)
        try:
            result.raw = RawExtraction.model_validate_json(response.text)
        except ValidationError as error:
            schema_failures += 1
            result.attempts.append({"outcome": SCHEMA_VALIDATION_FAILED})
            if schema_failures < SCHEMA_ATTEMPTS:
                continue
            result.error_code = SCHEMA_VALIDATION_FAILED
            result.error_message = _summarize(error)
            return result
        result.attempts.append({"outcome": "ok"})
        return result
