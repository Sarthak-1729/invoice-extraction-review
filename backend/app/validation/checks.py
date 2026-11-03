"""Run every document-independent check on a raw extraction.

The grounding check needs the PDF text and is added in Phase 4.
"""

from dataclasses import dataclass

from app.normalize import normalize
from app.schemas.invoice import Invoice, RawExtraction
from app.validation.arithmetic import check_arithmetic
from app.validation.consistency import check_consistency
from app.validation.flags import Flag


@dataclass
class CheckResult:
    invoice: Invoice
    flags: list[Flag]


def check_invoice(raw: RawExtraction) -> CheckResult:
    normalized = normalize(raw)
    flags = [
        *normalized.flags,
        *check_arithmetic(normalized.invoice),
        *check_consistency(raw, normalized.invoice),
    ]
    return CheckResult(invoice=normalized.invoice, flags=flags)
