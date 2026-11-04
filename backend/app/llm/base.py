"""Provider interface: send the prompt, get back the model's raw JSON text.

Providers do not parse or trust the output; ``app.extraction`` validates it.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMErrorCode:
    RATE_LIMITED = "LLM_RATE_LIMITED"  # 429
    UNAVAILABLE = "LLM_UNAVAILABLE"  # 500, 503, 504, connection errors
    TIMEOUT = "LLM_TIMEOUT"
    AUTH_FAILED = "LLM_AUTH_FAILED"  # 401, 403
    BAD_REQUEST = "LLM_BAD_REQUEST"  # 400, 404 (e.g. unknown model) and other 4xx
    NOT_CONFIGURED = "LLM_NOT_CONFIGURED"  # missing API key or model name
    INCOMPLETE = "LLM_OUTPUT_INCOMPLETE"  # stopped early (e.g. output token limit)
    ERROR = "LLM_ERROR"  # anything else


RETRYABLE = {LLMErrorCode.RATE_LIMITED, LLMErrorCode.UNAVAILABLE, LLMErrorCode.TIMEOUT}


class LLMError(Exception):
    def __init__(self, code: str, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after  # seconds, from the provider when it says

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        """Return the model's JSON text, or raise ``LLMError``."""
        ...
