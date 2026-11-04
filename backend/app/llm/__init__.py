"""LLM providers. ``get_provider`` builds the one selected by LLM_PROVIDER."""

from app.config import Settings
from app.llm.base import LLMError, LLMErrorCode, LLMProvider, LLMResponse
from app.llm.fake import FakeProvider

__all__ = [
    "FakeProvider",
    "LLMError",
    "LLMErrorCode",
    "LLMProvider",
    "LLMResponse",
    "get_provider",
]


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider == "gemini":
        from app.llm.gemini import GeminiProvider

        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
        return GeminiProvider(
            key,
            settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_output_tokens=settings.gemini_max_output_tokens,
            thinking_level=settings.gemini_thinking_level,
            min_interval_seconds=settings.gemini_min_interval_seconds,
        )
    raise LLMError(
        LLMErrorCode.NOT_CONFIGURED, f"Provider {settings.llm_provider!r} is not available."
    )
