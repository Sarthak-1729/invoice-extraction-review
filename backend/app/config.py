"""Application settings, read from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["gemini", "fake", "ollama"] = "fake"
    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None

    database_url: str = "sqlite:///./data/app.sqlite3"
    upload_dir: Path = Path("./uploads")

    max_upload_mb: int = Field(default=10, gt=0)
    max_pages: int = Field(default=20, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
