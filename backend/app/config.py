"""Application settings, read from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # The repo-root .env, then one in the working directory (which wins).
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    llm_provider: Literal["gemini", "fake", "ollama"] = "fake"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    # Pacing for the free tier: minimum seconds between requests. The docs do
    # not publish free-tier numbers; check your limits in Google AI Studio.
    gemini_min_interval_seconds: float = Field(default=6.0, ge=0)
    gemini_timeout_seconds: float = Field(default=120.0, gt=0)
    gemini_max_output_tokens: int = Field(default=16384, gt=0)
    # minimal | low | medium | high; unset keeps the model default.
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] | None = None
    # Retries after 429 / 503 / timeouts, on top of the first attempt.
    llm_transient_retries: int = Field(default=3, ge=0)
    llm_max_backoff_seconds: float = Field(default=60.0, gt=0)

    database_url: str = "sqlite:///./data/app.sqlite3"
    upload_dir: Path = Path("./uploads")

    max_upload_mb: int = Field(default=10, gt=0)
    max_pages: int = Field(default=20, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
