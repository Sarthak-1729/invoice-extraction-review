# syntax=docker/dockerfile:1
# Backend API image. Build from the repo root (see docker-compose.yml):
#   docker build -f backend/Dockerfile -t invoice-review-backend .
# No secrets are copied: the root .dockerignore allows only the files below.
# The API key and settings come from the environment at run time (.env via
# docker compose).

# Python 3.11.9, the version every test and CI run uses (pinned by digest).
FROM python:3.11.9-slim-bookworm@sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
# Only the hashes of the held-out sets (no PDFs, no truth files), so the
# upload guard still refuses test-set and hand-made PDFs inside the container.
# The guard finds them relative to the source tree, hence the editable install.
COPY eval/datasets/test/MANIFEST.sha256 /app/eval/datasets/test/MANIFEST.sha256
COPY eval/handmade/CHANGELOG.md eval/handmade/MANIFEST.sha25[6] /app/eval/handmade/

RUN pip install -e . \
    && mkdir -p /data/uploads \
    && chown -R app:app /data

ENV DATABASE_URL=sqlite:////data/app.sqlite3 \
    UPLOAD_DIR=/data/uploads
VOLUME ["/data"]

USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# One worker: SQLite, and the provider's request pacing lives in one process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
