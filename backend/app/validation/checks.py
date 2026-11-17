"""Run every check on a raw extraction.

Grounding needs the PDF text; without ``document_text`` it is skipped (used
by tests and by callers that only normalize).
"""

from dataclasses import dataclass

from app.normalize import normalize
from app.schemas.invoice import Invoice, RawExtraction
from app.validation.arithmetic import check_arithmetic
from app.validation.consistency import check_consistency
from app.validation.flags import Flag
from app.validation.grounding import check_grounding


@dataclass
class CheckResult:
    invoice: Invoice
    flags: list[Flag]


def check_invoice(raw: RawExtraction, document_text: str | None = None) -> CheckResult:
    normalized = normalize(raw)
    flags = [
        *normalized.flags,
        *check_arithmetic(normalized.invoice),
        *check_consistency(raw, normalized.invoice),
    ]
    if document_text is not None:
        flags += check_grounding(raw, document_text)
    return CheckResult(invoice=normalized.invoice, flags=flags)
