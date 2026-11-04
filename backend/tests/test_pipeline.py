"""Pipeline, test-set guard and CLI, with the fake provider only."""

import hashlib
import json
import shutil

import pytest

from app import extract
from app.config import Settings
from app.llm import FakeProvider, LLMError, LLMErrorCode
from app.pdf_text import PdfRejected
from app.pipeline import run_pipeline
from app.testset_guard import TEST_SET_DIR, TestSetGuardError, guard_test_set, is_test_set_file
from tests.pdf_factory import image_only_pdf, text_pdf

CONSISTENT = {
    "invoice_number": "INV-1042",
    "vendor_name": "Acme Ltd",
    "bill_to_name": None,
    "invoice_date": "2026-03-25",
    "due_date": None,
    "currency": "USD",
    "subtotal": "1,234.50",
    "tax": None,
    "total": "1,234.50 USD",
    "line_items": [
        {"description": "Widget", "quantity": "1", "unit_price": "1,234.50", "amount": "1,234.50"}
    ],
}
SETTINGS = Settings(_env_file=None, llm_provider="fake")


def test_consistent_extraction_has_status_extracted(tmp_path):
    provider = FakeProvider([json.dumps(CONSISTENT)])
    result = run_pipeline(text_pdf(tmp_path / "a.pdf"), provider, SETTINGS)
    assert result.status == "extracted" and result.flags == []
    assert str(result.invoice.total) == "1234.50"
    assert result.prompt_version == "extraction_v1" and len(result.prompt_hash) == 64
    assert "[pdf page 1 of 1]" in provider.calls[0]["user"]


def test_arithmetic_problem_needs_review(tmp_path):
    wrong_total = CONSISTENT | {"total": "1,300.00 USD"}
    result = run_pipeline(
        text_pdf(tmp_path / "a.pdf"), FakeProvider([json.dumps(wrong_total)]), SETTINGS
    )
    assert result.status == "needs_review"
    assert "TOTAL_MISMATCH" in {flag.code for flag in result.flags}


def test_provider_failure_gives_failed_status_with_code(tmp_path):
    provider = FakeProvider([LLMError(LLMErrorCode.AUTH_FAILED, "bad key")])
    result = run_pipeline(text_pdf(tmp_path / "a.pdf"), provider, SETTINGS)
    assert result.status == "failed" and result.error_code == LLMErrorCode.AUTH_FAILED
    assert result.to_dict()["error"] == {"code": "LLM_AUTH_FAILED", "message": "bad key"}


def test_schema_failure_gives_failed_status(tmp_path):
    result = run_pipeline(text_pdf(tmp_path / "a.pdf"), FakeProvider(["[]"]), SETTINGS)
    assert result.status == "failed" and result.error_code == "SCHEMA_VALIDATION_FAILED"


def test_scanned_pdf_is_rejected_before_calling_the_model(tmp_path):
    provider = FakeProvider()
    with pytest.raises(PdfRejected):
        run_pipeline(image_only_pdf(tmp_path / "scan.pdf"), provider, SETTINGS)
    assert provider.calls == []


# --- test-set guard ---------------------------------------------------------


def _fake_test_set(tmp_path):
    test_dir = tmp_path / "datasets" / "test"
    (test_dir / "pdf").mkdir(parents=True)
    pdf = text_pdf(test_dir / "pdf" / "t.pdf")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    (test_dir / "MANIFEST.sha256").write_text(f"{digest}  pdf/t.pdf\n")
    return test_dir, pdf


def test_guard_blocks_paths_inside_the_test_set(tmp_path):
    test_dir, pdf = _fake_test_set(tmp_path)
    with pytest.raises(TestSetGuardError):
        guard_test_set(pdf, allow_test_set=False, test_dir=test_dir)
    guard_test_set(pdf, allow_test_set=True, test_dir=test_dir)


def test_guard_catches_a_copy_by_hash(tmp_path):
    test_dir, pdf = _fake_test_set(tmp_path)
    copy = tmp_path / "elsewhere" / "renamed.pdf"
    copy.parent.mkdir()
    shutil.copy(pdf, copy)
    assert is_test_set_file(copy, test_dir)
    other = text_pdf(tmp_path / "other.pdf", lines=["different text for a different hash"] * 3)
    assert not is_test_set_file(other, test_dir)


def test_every_real_test_set_pdf_is_guarded():
    pdfs = sorted((TEST_SET_DIR / "pdf").glob("*.pdf"))
    assert len(pdfs) == 24
    assert all(is_test_set_file(pdf) for pdf in pdfs)


# --- CLI --------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_settings(monkeypatch):
    """The CLI must never read a developer's .env (and API key) during tests."""
    monkeypatch.setattr(extract, "Settings", lambda **kw: Settings(_env_file=None, **kw))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def test_cli_refuses_the_test_set_without_the_flag(capsys):
    code = extract.main([str(TEST_SET_DIR / "pdf" / "test-01.pdf"), "--provider", "fake"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "TEST_SET_GUARD"


def test_cli_prints_raw_normalized_and_flags(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(extract, "get_provider", lambda s: FakeProvider([json.dumps(CONSISTENT)]))
    code = extract.main([str(text_pdf(tmp_path / "a.pdf")), "--provider", "fake"])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["status"] == "extracted"
    assert output["raw"]["total"] == "1,234.50 USD"
    assert output["normalized"]["total"] == "1234.50"
    assert output["flags"] == [] and output["error"] is None


def test_cli_reports_rejected_pdf(tmp_path, capsys):
    code = extract.main([str(image_only_pdf(tmp_path / "scan.pdf")), "--provider", "fake"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "SCANNED_PDF_UNSUPPORTED"


def test_cli_gemini_without_key_fails_cleanly(tmp_path, capsys):
    code = extract.main([str(text_pdf(tmp_path / "a.pdf")), "--provider", "gemini"])
    assert code == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "LLM_NOT_CONFIGURED"
