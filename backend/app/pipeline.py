"""PDF -> text -> raw extraction -> normalization -> flags. No database yet.

PDF problems (scanned, encrypted, too many pages) raise ``PdfRejected``: they
are upload rejections, not failed extractions. Provider and schema failures
return a result with status ``failed`` and an error code.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.config import Settings
from app.extraction import extract_raw
from app.llm.base import LLMProvider
from app.pdf_text import extract_text
from app.prompt import load_prompt
from app.schemas.invoice import Invoice, RawExtraction
from app.validation.checks import check_invoice
from app.validation.flags import Flag

Status = Literal["extracted", "needs_review", "failed"]


@dataclass
class PipelineResult:
    status: Status
    page_count: int
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    raw: RawExtraction | None = None
    invoice: Invoice | None = None
    flags: list[Flag] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    usage: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "page_count": self.page_count,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "error": (
                {"code": self.error_code, "message": self.error_message}
                if self.error_code
                else None
            ),
            "raw": self.raw.model_dump() if self.raw else None,
            "normalized": self.invoice.model_dump(mode="json") if self.invoice else None,
            "flags": [flag.model_dump(mode="json") for flag in self.flags],
            "attempts": self.attempts,
            "usage": self.usage,
        }


def run_pipeline(
    pdf_path: Path,
    provider: LLMProvider,
    settings: Settings,
    prompt_version: str | None = None,
) -> PipelineResult:
    """``prompt_version`` selects a candidate prompt; None uses the active one."""
    pdf = extract_text(pdf_path, max_pages=settings.max_pages)
    prompt = load_prompt(prompt_version) if prompt_version else load_prompt()
    extraction = extract_raw(
        pdf.text,
        provider,
        prompt=prompt,
        transient_retries=settings.llm_transient_retries,
        max_backoff=settings.llm_max_backoff_seconds,
    )
    result = PipelineResult(
        status="failed",
        page_count=pdf.page_count,
        provider=provider.name,
        model=provider.model,
        prompt_version=prompt.version,
        prompt_hash=prompt.sha256,
        raw=extraction.raw,
        error_code=extraction.error_code,
        error_message=extraction.error_message,
        attempts=extraction.attempts,
        usage=extraction.usage,
    )
    if extraction.raw is None:
        return result

    checked = check_invoice(extraction.raw, document_text=pdf.text)
    result.invoice, result.flags = checked.invoice, checked.flags
    result.status = "needs_review" if checked.flags else "extracted"
    return result
