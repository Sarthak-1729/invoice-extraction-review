"""Repository and review rules on a temporary SQLite database."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Correction, Document, FlagRow, create_schema, make_engine, make_session_factory
from app.pipeline import PipelineResult
from app.repository import DocumentRepository, FieldChange, ReviewError
from app.schemas.invoice import RawExtraction
from app.validation.checks import check_invoice

TEXT = "\n".join(
    [
        "Acme Ltd INVOICE",
        "Invoice No: INV-1042 Date: 2026-03-25 Currency: USD",
        "Widget 1 1,234.50 1,234.50",
        "Subtotal: 1,234.50",
        "Total: 1,234.50 USD",
    ]
)
RAW = {
    "invoice_number": "INV-1042",
    "vendor_name": "Acme Ltd",
    "invoice_date": "2026-03-25",
    "currency": "USD",
    "subtotal": "1,234.50",
    "total": "1,234.50 USD",
    "line_items": [
        {"description": "Widget", "quantity": "1", "unit_price": "1,234.50", "amount": "1,234.50"}
    ],
}


@pytest.fixture
def repo(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'data' / 'test.sqlite3'}")
    create_schema(engine)
    with make_session_factory(engine)() as session:
        yield DocumentRepository(session)
    engine.dispose()


def result(raw=None, error=None):
    common = dict(
        page_count=1,
        provider="fake",
        model="fake-model",
        prompt_version="extraction_v4",
        prompt_hash="0" * 64,
    )
    if error:
        return PipelineResult(status="failed", error_code=error, error_message="boom", **common)
    model = RawExtraction.model_validate(raw)
    checked = check_invoice(model, document_text=TEXT)
    status = "needs_review" if checked.flags else "extracted"
    return PipelineResult(
        status=status, raw=model, invoice=checked.invoice, flags=checked.flags, **common
    )


def new_document(sha="a" * 64, doc_id="d1"):
    return Document(
        id=doc_id,
        sha256=sha,
        display_name="invoice.pdf",
        stored_name=f"{doc_id}.pdf",
        size_bytes=100,
        page_count=1,
        document_text=TEXT,
    )


def test_clean_extraction_is_extracted(repo):
    doc = repo.add(new_document(), result(RAW))
    assert doc.status == "extracted" and doc.flags == []
    assert doc.normalized["total"] == "1234.50"
    assert repo.get_by_sha256("a" * 64).id == "d1"


def test_flags_are_stored_and_status_is_needs_review(repo):
    doc = repo.add(new_document(), result(RAW | {"total": "1,300.00 USD"}))
    assert doc.status == "needs_review"
    codes = {(f.field_path, f.code) for f in doc.flags}
    assert ("total", "TOTAL_MISMATCH") in codes
    assert ("total", "VALUE_NOT_IN_DOCUMENT") in codes  # 1,300.00 is not printed


def test_failed_extraction_keeps_its_error(repo):
    doc = repo.add(new_document(), result(error="LLM_UNAVAILABLE"))
    assert (doc.status, doc.error_code, doc.raw) == ("failed", "LLM_UNAVAILABLE", None)


def test_correction_writes_audit_trail_and_revalidates(repo):
    doc = repo.add(new_document(), result(RAW | {"total": "1,300.00 USD"}))
    doc = repo.apply_changes(doc, [FieldChange("total", "1,234.50 USD")])
    assert doc.status == "extracted" and doc.flags == []
    [correction] = doc.corrections
    assert (correction.field_path, correction.original_value, correction.corrected_value) == (
        "total",
        "1,300.00 USD",
        "1,234.50 USD",
    )
    assert correction.created_at is not None


def test_grounding_is_not_applied_to_corrected_fields(repo):
    doc = repo.add(new_document(), result(RAW))
    # The reviewer types a value that is not printed (for example a known fix).
    doc = repo.apply_changes(doc, [FieldChange("vendor_name", "Acme Limited")])
    assert not any(f.code == "VALUE_NOT_IN_DOCUMENT" for f in doc.flags)
    assert doc.corrected_paths == ["vendor_name"]


def test_corrections_on_line_items_and_to_null(repo):
    doc = repo.add(new_document(), result(RAW))
    doc = repo.apply_changes(
        doc,
        [FieldChange("line_items[0].description", "Widget XL"), FieldChange("currency", "")],
    )
    assert doc.raw["line_items"][0]["description"] == "Widget XL"
    assert doc.raw["currency"] is None
    assert [c.field_path for c in doc.corrections] == ["line_items[0].description", "currency"]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ([FieldChange("confidence", "0.9")], "UNKNOWN_FIELD"),
        ([FieldChange("line_items[5].amount", "1")], "UNKNOWN_FIELD"),
        ([FieldChange("line_items[0].sku", "1")], "UNKNOWN_FIELD"),
        ([FieldChange("total", "1,234.50 USD")], "NO_CHANGES"),
        ([], "NO_CHANGES"),
        ([FieldChange("total", "9" * 501)], "INVALID_VALUE"),
    ],
)
def test_invalid_corrections_are_rejected_without_writes(repo, changes, code):
    doc = repo.add(new_document(), result(RAW))
    with pytest.raises(ReviewError) as info:
        repo.apply_changes(doc, changes)
    assert info.value.code == code
    repo.session.rollback()
    assert repo.session.scalars(select(Correction)).all() == []


def test_approval_needs_acknowledged_flags_then_locks(repo):
    doc = repo.add(new_document(), result(RAW | {"total": "1,300.00 USD"}))
    with pytest.raises(ReviewError) as info:
        repo.approve(doc, acknowledge_open_flags=False)
    assert (info.value.status, info.value.code) == (409, "OPEN_FLAGS")

    doc = repo.approve(doc, acknowledge_open_flags=True)
    assert doc.status == "approved" and doc.acknowledged_open_flags and doc.approved_at
    with pytest.raises(ReviewError) as info:
        repo.apply_changes(doc, [FieldChange("total", "1,234.50 USD")])
    assert info.value.code == "DOCUMENT_LOCKED"
    with pytest.raises(ReviewError) as info:
        repo.approve(doc, acknowledge_open_flags=True)
    assert info.value.code == "ALREADY_APPROVED"


def test_clean_document_approves_without_acknowledgement(repo):
    doc = repo.approve(repo.add(new_document(), result(RAW)), acknowledge_open_flags=False)
    assert doc.status == "approved" and not doc.acknowledged_open_flags


def test_failed_documents_cannot_be_edited_or_approved_but_can_be_retried(repo):
    doc = repo.add(new_document(), result(error="LLM_UNAVAILABLE"))
    for action in (
        lambda: repo.apply_changes(doc, [FieldChange("total", "1")]),
        lambda: repo.approve(doc, acknowledge_open_flags=True),
    ):
        with pytest.raises(ReviewError):
            action()
    doc = repo.replace_extraction(doc, result(RAW))
    assert doc.status == "extracted" and doc.error_code is None
    with pytest.raises(ReviewError) as info:
        repo.replace_extraction(doc, result(RAW))
    assert info.value.code == "RETRY_NOT_ALLOWED"


def test_list_filters_by_status(repo):
    repo.add(new_document("a" * 64, "d1"), result(RAW))
    repo.add(new_document("b" * 64, "d2"), result(error="LLM_TIMEOUT"))
    assert {d.id for d in repo.list_documents()} == {"d1", "d2"}
    assert [d.id for d in repo.list_documents("failed")] == ["d2"]


def test_sha256_is_unique(repo):
    repo.add(new_document("a" * 64, "d1"), result(RAW))
    with pytest.raises(IntegrityError):
        repo.add(new_document("a" * 64, "d2"), result(RAW))


def test_delete_removes_flags_and_corrections(repo):
    doc = repo.add(new_document(), result(RAW | {"total": "1,300.00 USD"}))
    repo.apply_changes(doc, [FieldChange("tax", "65.50")])
    repo.delete(doc)
    assert repo.session.scalars(select(FlagRow)).all() == []
    assert repo.session.scalars(select(Correction)).all() == []
