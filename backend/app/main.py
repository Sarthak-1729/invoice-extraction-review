"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    app = FastAPI(title="Invoice Extraction with Human Review", version=__version__)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
