"""FastAPI application entry point.

Run from backend/: uvicorn app.main:app
The database, upload folder and LLM provider are created on first use, so
building the app has no side effects.
"""

from functools import cached_property
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import ApiError, error_response, router
from app.config import Settings, get_settings
from app.db import create_schema, make_engine, make_session_factory
from app.llm import get_provider
from app.llm.base import LLMProvider
from app.repository import ReviewError

_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


class Services:
    def __init__(self, settings: Settings, provider: LLMProvider | None = None) -> None:
        self.settings = settings
        self._provider = provider
        self._lock = Lock()

    @cached_property
    def engine(self) -> Engine:
        engine = make_engine(self.settings.database_url)
        create_schema(engine)
        return engine

    @cached_property
    def sessions(self) -> sessionmaker[Session]:
        return make_session_factory(self.engine)

    def upload_dir(self) -> Path:
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        return self.settings.upload_dir

    def provider(self) -> LLMProvider:
        """One provider for the app, so request pacing applies across requests."""
        with self._lock:
            if self._provider is None:
                self._provider = get_provider(self.settings)
            return self._provider


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    app = FastAPI(title="Invoice Extraction with Human Review", version=__version__)
    app.state.services = Services(settings or get_settings(), provider)
    app.include_router(router)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError):
        return error_response(error.status, error.code, error.message, **error.extra)

    @app.exception_handler(ReviewError)
    async def review_error(request: Request, error: ReviewError):
        return error_response(error.status, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        first = error.errors()[0] if error.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()))
        return error_response(422, "VALIDATION_ERROR", f"{where}: {first.get('msg', 'invalid')}")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException):
        code = _HTTP_CODES.get(error.status_code, f"HTTP_{error.status_code}")
        return error_response(error.status_code, code, str(error.detail))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        return error_response(500, "INTERNAL_ERROR", "Unexpected server error.")

    return app


app = create_app()
