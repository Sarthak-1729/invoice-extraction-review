"""HTTP API (docs/DESIGN.md). Every error uses {"error": {"code", "message"}}.

Extraction runs synchronously inside the upload and retry requests, through
the same pipeline as the CLI, with the active prompt.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import STATUSES, Document, iso_utc
from app.export import export_csv, export_record
from app.llm import LLMError
from app.llm.base import LLMProvider
from app.pdf_text import PDF_MAGIC, PdfRejected, check_upload, extract_text, sanitize_filename
from app.pipeline import PipelineResult, run_pipeline
from app.prompt import load_prompt
from app.repository import DocumentRepository, FieldChange
from app.testset_guard import is_test_set_sha256

router = APIRouter(prefix="/api")
CHUNK = 64 * 1024
_PDF_STATUS = {"FILE_TOO_LARGE": 413, "NOT_A_PDF": 415}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def error_response(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


# --- request bodies -----------------------------------------------------------


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_path: str = Field(max_length=100)
    value: str | None = Field(default=None, max_length=500)


class ChangesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: list[Change] = Field(max_length=200)


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acknowledge_open_flags: bool = False


# --- dependencies -------------------------------------------------------------


def get_session(request: Request):
    with request.app.state.services.sessions() as session:
        yield session


def get_repo(session: Annotated[Session, Depends(get_session)]) -> DocumentRepository:
    return DocumentRepository(session)


Repo = Annotated[DocumentRepository, Depends(get_repo)]


def _found(repo: DocumentRepository, document_id: str) -> Document:
    document = repo.get(document_id) if len(document_id) <= 32 else None
    if document is None:
        raise ApiError(404, "NOT_FOUND", "No document with this id.")
    return document


# --- serialization ------------------------------------------------------------


def _time(value) -> str | None:
    return iso_utc(value)


def summary(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "file_name": document.display_name,
        "status": document.status,
        "flag_count": len(document.flags),
        "error_code": document.error_code,
        "retry_available": document.status == "failed",
        "created_at": _time(document.created_at),
        "approved_at": _time(document.approved_at),
    }


def detail(document: Document) -> dict[str, Any]:
    return {
        **summary(document),
        "sha256": document.sha256,
        "size_bytes": document.size_bytes,
        "page_count": document.page_count,
        "error": (
            {"code": document.error_code, "message": document.error_message}
            if document.error_code
            else None
        ),
        "provider": document.provider,
        "model": document.model,
        "prompt_version": document.prompt_version,
        "prompt_hash": document.prompt_hash,
        "raw": document.raw,
        "normalized": document.normalized,
        "flags": [
            {
                "field_path": f.field_path,
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
            }
            for f in document.flags
        ],
        "corrected_paths": document.corrected_paths or [],
        "corrections": [correction_dict(c) for c in document.corrections],
        "acknowledged_open_flags": document.acknowledged_open_flags,
        "updated_at": _time(document.updated_at),
    }


def correction_dict(correction) -> dict[str, Any]:
    return {
        "field_path": correction.field_path,
        "original_value": correction.original_value,
        "corrected_value": correction.corrected_value,
        "created_at": _time(correction.created_at),
    }


# --- extraction ---------------------------------------------------------------


def _extract(request: Request, path: Path) -> tuple[PipelineResult, str]:
    """PDF text, then the pipeline. PdfRejected propagates (no document is kept)."""
    services = request.app.state.services
    settings: Settings = services.settings
    text = extract_text(path, max_pages=settings.max_pages)
    try:
        provider: LLMProvider = services.provider()
    except LLMError as error:  # e.g. no API key: a failed document, retry later
        prompt = load_prompt()
        return PipelineResult(
            status="failed",
            page_count=text.page_count,
            provider=settings.llm_provider,
            model=settings.gemini_model or "",
            prompt_version=prompt.version,
            prompt_hash=prompt.sha256,
            error_code=error.code,
            error_message=error.message,
        ), text.text
    return run_pipeline(path, provider, settings), text.text


def _pdf_error(error: PdfRejected) -> ApiError:
    return ApiError(_PDF_STATUS.get(error.code, 422), error.code, error.message)


# --- endpoints ----------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/documents", status_code=201)
def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    repo: Repo,
):
    services = request.app.state.services
    settings: Settings = services.settings
    max_bytes = settings.max_upload_mb * 2**20
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes + CHUNK:
        raise ApiError(413, "FILE_TOO_LARGE", f"File is larger than {settings.max_upload_mb} MB.")

    upload_dir = services.upload_dir()
    incoming = upload_dir / f".incoming-{uuid.uuid4().hex}.part"
    digest, size, head = hashlib.sha256(), 0, b""
    try:
        with incoming.open("wb") as out:
            while chunk := file.file.read(CHUNK):
                if not head:
                    head = chunk[: len(PDF_MAGIC)]
                size += len(chunk)
                if size > max_bytes:
                    raise ApiError(
                        413, "FILE_TOO_LARGE", f"File is larger than {settings.max_upload_mb} MB."
                    )
                digest.update(chunk)
                out.write(chunk)
        try:
            check_upload(file.filename, file.content_type, head, size, max_bytes)
        except PdfRejected as error:
            raise _pdf_error(error) from error

        sha256 = digest.hexdigest()
        if is_test_set_sha256(sha256) and not settings.allow_test_set_uploads:
            raise ApiError(
                403,
                "TEST_SET_DOCUMENT",
                "This PDF is part of the frozen test set. Uploads of test-set documents are "
                "disabled (ALLOW_TEST_SET_UPLOADS is false; only the Phase 7 evaluation sets it).",
            )
        existing = repo.get_by_sha256(sha256)
        if existing is not None:
            if existing.status == "failed":
                return JSONResponse(detail(existing), status_code=200)
            raise ApiError(
                409, "DUPLICATE", "This PDF was already uploaded.", document_id=existing.id
            )

        document_id = uuid.uuid4().hex
        stored = upload_dir / f"{document_id}.pdf"
        incoming.replace(stored)
    finally:
        incoming.unlink(missing_ok=True)

    try:
        result, text = _extract(request, stored)
    except PdfRejected as error:
        stored.unlink(missing_ok=True)
        raise _pdf_error(error) from error
    document = Document(
        id=document_id,
        sha256=sha256,
        display_name=sanitize_filename(file.filename),
        stored_name=stored.name,
        size_bytes=size,
        page_count=result.page_count,
        document_text=text,
    )
    try:
        repo.add(document, result)
    except IntegrityError as error:  # the same file uploaded twice at once
        repo.session.rollback()
        stored.unlink(missing_ok=True)
        raise ApiError(409, "DUPLICATE", "This PDF was already uploaded.") from error
    return detail(document)


@router.get("/documents")
def list_documents(
    repo: Repo,
    status: Annotated[str | None, Query()] = None,
):
    if status is not None and status not in STATUSES:
        raise ApiError(422, "INVALID_STATUS", f"status must be one of {', '.join(STATUSES)}.")
    return {"documents": [summary(d) for d in repo.list_documents(status)]}


@router.get("/documents/{document_id}")
def get_document(document_id: str, repo: Repo):
    return detail(_found(repo, document_id))


@router.get("/documents/{document_id}/pdf")
def get_pdf(document_id: str, request: Request, repo: Repo):
    document = _found(repo, document_id)
    path = request.app.state.services.upload_dir() / document.stored_name  # never user input
    if not path.is_file():
        raise ApiError(404, "FILE_MISSING", "The stored PDF is missing.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.display_name,
        content_disposition_type="inline",
    )


@router.post("/documents/{document_id}/retry")
def retry_extraction(document_id: str, request: Request, repo: Repo):
    document = _found(repo, document_id)
    if document.status != "failed":
        raise ApiError(409, "RETRY_NOT_ALLOWED", "Only failed documents can be retried.")
    path = request.app.state.services.upload_dir() / document.stored_name
    try:
        result, text = _extract(request, path)
    except PdfRejected as error:
        raise _pdf_error(error) from error
    document.document_text = text
    return detail(repo.replace_extraction(document, result))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, request: Request, repo: Repo):
    document = _found(repo, document_id)
    stored = request.app.state.services.upload_dir() / document.stored_name
    repo.delete(document)
    stored.unlink(missing_ok=True)
    return Response(status_code=204)


@router.patch("/documents/{document_id}/fields")
def update_fields(document_id: str, body: ChangesRequest, repo: Repo):
    document = _found(repo, document_id)
    changes = [FieldChange(c.field_path, c.value) for c in body.changes]
    return detail(repo.apply_changes(document, changes))


@router.post("/documents/{document_id}/approve")
def approve_document(
    document_id: str,
    repo: Repo,
    body: ApproveRequest | None = None,
):
    document = _found(repo, document_id)
    acknowledge = body.acknowledge_open_flags if body else False
    return detail(repo.approve(document, acknowledge))


@router.get("/documents/{document_id}/corrections")
def list_corrections(document_id: str, repo: Repo):
    document = _found(repo, document_id)
    return {"corrections": [correction_dict(c) for c in document.corrections]}


@router.get("/export")
def export(
    repo: Repo,
    format: Annotated[Literal["json", "csv"], Query()] = "json",
):
    documents = repo.approved()  # approved only; failed documents are never exported
    if format == "csv":
        return Response(
            export_csv(documents),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="invoices.csv"'},
        )
    return {"documents": [export_record(d) for d in documents]}
