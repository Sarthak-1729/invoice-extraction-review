"""Documents in the database, and the review rules that change them.

Rules:
- Status after extraction or a correction: ``needs_review`` if any flag is
  open, else ``extracted``. ``failed`` keeps the provider or schema error code.
- Corrections replace the raw string of one field, write an audit row
  (original and corrected value, timestamp) and re-run every check. Grounding
  is not applied to fields a reviewer has corrected: the reviewer is the
  source for those values.
- Approval needs every open flag acknowledged; an approved document is locked.
"""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Correction, Document, FlagRow, utcnow
from app.pipeline import PipelineResult
from app.schemas.invoice import RawExtraction
from app.validation.checks import check_invoice
from app.validation.flags import Flag

HEADER_FIELDS = (
    "invoice_number",
    "vendor_name",
    "bill_to_name",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "tax",
    "total",
)
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")
_LINE_PATH = re.compile(r"line_items\[(\d+)\]\.(" + "|".join(LINE_FIELDS) + r")")


class ReviewError(Exception):
    """A rule was violated. ``status`` is the HTTP status the API should use."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class FieldChange:
    field_path: str
    value: str | None


def _status_for(flags: list[Any]) -> str:
    return "needs_review" if flags else "extracted"


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- queries -------------------------------------------------------------

    def get(self, document_id: str) -> Document | None:
        return self.session.get(Document, document_id)

    def get_by_sha256(self, sha256: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.sha256 == sha256))

    def list_documents(self, status: str | None = None) -> list[Document]:
        query = select(Document).order_by(Document.created_at.desc(), Document.id)
        if status:
            query = query.where(Document.status == status)
        return list(self.session.scalars(query))

    def approved(self) -> list[Document]:
        query = select(Document).where(Document.status == "approved")
        return list(self.session.scalars(query.order_by(Document.approved_at, Document.id)))

    # --- writes --------------------------------------------------------------

    def add(self, document: Document, result: PipelineResult) -> Document:
        self._apply_result(document, result)
        self.session.add(document)
        self.session.commit()
        return document

    def replace_extraction(self, document: Document, result: PipelineResult) -> Document:
        """Retry: a new extraction replaces the failed one."""
        if document.status != "failed":
            raise ReviewError(409, "RETRY_NOT_ALLOWED", "Only failed documents can be retried.")
        document.corrected_paths = []
        self._apply_result(document, result)
        self.session.commit()
        return document

    def apply_changes(self, document: Document, changes: list[FieldChange]) -> Document:
        if document.status == "approved":
            raise ReviewError(409, "DOCUMENT_LOCKED", "Approved documents cannot be edited.")
        if document.status == "failed" or document.raw is None:
            raise ReviewError(409, "NO_EXTRACTION", "A failed document has no fields to edit.")
        if not changes:
            raise ReviewError(422, "NO_CHANGES", "No changes were given.")

        raw = {**document.raw, "line_items": [dict(li) for li in document.raw["line_items"]]}
        corrections = []
        for change in changes:
            original = self._get(raw, change.field_path)
            value = change.value.strip() if isinstance(change.value, str) else None
            value = value or None
            if value == original:
                continue
            self._set(raw, change.field_path, value)
            corrections.append(
                Correction(
                    field_path=change.field_path, original_value=original, corrected_value=value
                )
            )
        if not corrections:
            raise ReviewError(422, "NO_CHANGES", "Every value is the same as before.")
        try:
            validated = RawExtraction.model_validate(raw)
        except ValidationError as error:
            first = error.errors()[0]
            raise ReviewError(422, "INVALID_VALUE", first["msg"]) from error

        document.corrections.extend(corrections)
        paths = set(document.corrected_paths or []) | {c.field_path for c in corrections}
        document.corrected_paths = sorted(paths)
        self._revalidate(document, validated)
        document.acknowledged_open_flags = False
        self.session.commit()
        return document

    def approve(self, document: Document, acknowledge_open_flags: bool) -> Document:
        if document.status == "approved":
            raise ReviewError(409, "ALREADY_APPROVED", "The document is already approved.")
        if document.status == "failed":
            raise ReviewError(409, "NOT_APPROVABLE", "Failed documents cannot be approved.")
        if document.flags and not acknowledge_open_flags:
            raise ReviewError(
                409,
                "OPEN_FLAGS",
                f"{len(document.flags)} open flag(s). Correct them, or approve with "
                "acknowledge_open_flags=true.",
            )
        document.status = "approved"
        document.acknowledged_open_flags = bool(document.flags)
        document.approved_at = utcnow()
        self.session.commit()
        return document

    def delete(self, document: Document) -> None:
        self.session.delete(document)
        self.session.commit()

    # --- helpers -------------------------------------------------------------

    def _apply_result(self, document: Document, result: PipelineResult) -> None:
        document.page_count = result.page_count
        document.provider, document.model = result.provider, result.model
        document.prompt_version, document.prompt_hash = result.prompt_version, result.prompt_hash
        document.flags = []
        if result.status == "failed" or result.raw is None:
            document.status = "failed"
            document.error_code = result.error_code
            document.error_message = result.error_message
            document.raw = document.normalized = None
            return
        document.error_code = document.error_message = None
        document.raw = result.raw.model_dump()
        document.normalized = result.invoice.model_dump(mode="json")
        document.flags = [_flag_row(flag) for flag in result.flags]
        document.status = _status_for(result.flags)

    def _revalidate(self, document: Document, raw: RawExtraction) -> None:
        checked = check_invoice(raw, document_text=document.document_text)
        corrected = set(document.corrected_paths or [])
        flags = [
            flag
            for flag in checked.flags
            if not (flag.code == "VALUE_NOT_IN_DOCUMENT" and flag.field_path in corrected)
        ]
        document.raw = raw.model_dump()
        document.normalized = checked.invoice.model_dump(mode="json")
        document.flags = [_flag_row(flag) for flag in flags]
        document.status = _status_for(flags)

    @staticmethod
    def _locate(raw: dict[str, Any], path: str) -> tuple[dict[str, Any], str]:
        if path in HEADER_FIELDS:
            return raw, path
        match = _LINE_PATH.fullmatch(path)
        if match and int(match.group(1)) < len(raw["line_items"]):
            return raw["line_items"][int(match.group(1))], match.group(2)
        raise ReviewError(422, "UNKNOWN_FIELD", f"Unknown field path {path!r}.")

    def _get(self, raw: dict[str, Any], path: str) -> str | None:
        container, key = self._locate(raw, path)
        return container.get(key)

    def _set(self, raw: dict[str, Any], path: str, value: str | None) -> None:
        container, key = self._locate(raw, path)
        container[key] = value


def _flag_row(flag: Flag) -> FlagRow:
    return FlagRow(
        field_path=flag.field_path,
        code=str(flag.code),
        severity=str(flag.severity),
        message=flag.message,
    )
