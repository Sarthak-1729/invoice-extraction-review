"""API with the fake provider, a temporary database and real dev PDFs."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app import api
from app.config import Settings
from app.export import safe_cell
from app.llm import FakeProvider, LLMError, LLMErrorCode
from app.main import create_app
from app.testset_guard import REPO_ROOT
from tests.pdf_factory import encrypted_pdf, image_only_pdf

DEV = REPO_ROOT / "eval" / "datasets" / "dev"
TEST_PDF = REPO_ROOT / "eval" / "datasets" / "test" / "pdf" / "test-01.pdf"
TRUTHS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (DEV / "truth").glob("*.json")}


def perfect(doc_id: str) -> dict:
    t = TRUTHS[doc_id]
    raw = {k: f["printed"] for k, f in t["fields"].items()}
    raw["line_items"] = [{k: f["printed"] for k, f in li.items()} for li in t["line_items"]]
    return raw


class Model(FakeProvider):
    """Answers with the truth's printed values, optionally changed or failing."""

    def __init__(self):
        super().__init__([self._answer])
        self.overrides: dict[str, dict] = {}
        self.failures: dict[str, LLMError] = {}
        self.seen: list[str] = []

    def _answer(self, system, user):
        doc_id = next(
            d for d, t in TRUTHS.items() if t["fields"]["invoice_number"]["printed"] in user
        )
        self.seen.append(doc_id)
        if doc_id in self.failures:
            raise self.failures[doc_id]
        return json.dumps(perfect(doc_id) | self.overrides.get(doc_id, {}))


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        llm_provider="fake",
        llm_transient_retries=0,
        database_url=f"sqlite:///{(tmp_path / 'data' / 'app.sqlite3').as_posix()}",
        upload_dir=tmp_path / "uploads",
        max_upload_mb=1,
    )


@pytest.fixture
def model():
    return Model()


@pytest.fixture
def client(settings, model):
    app = create_app(settings, provider=model)
    with TestClient(app) as test_client:
        yield test_client
    app.state.services.engine.dispose()


def upload(client, path, name=None, content_type="application/pdf", data=None):
    content = data if data is not None else path.read_bytes()
    return client.post("/api/documents", files={"file": (name or path.name, content, content_type)})


def error(response):
    body = response.json()
    assert set(body) == {"error"} and {"code", "message"} <= set(body["error"])
    return body["error"]["code"]


# --- upload and status --------------------------------------------------------


def test_clean_upload_is_extracted_and_listed(client, settings):
    response = upload(client, DEV / "pdf" / "dev-01.pdf")
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "extracted" and doc["flags"] == []
    assert doc["prompt_version"] == "extraction_v4"
    assert doc["normalized"]["total"] == "35292.69"
    assert doc["raw"]["total"] == "$35,292.69"
    assert [d["id"] for d in client.get("/api/documents").json()["documents"]] == [doc["id"]]
    assert client.get(f"/api/documents/{doc['id']}").json()["sha256"] == doc["sha256"]
    stored = list(settings.upload_dir.iterdir())
    assert [p.name for p in stored] == [f"{doc['id']}.pdf"]  # uuid name, no temp files


def test_pdf_is_served_by_id(client):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    response = client.get(f"/api/documents/{doc['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == (DEV / "pdf" / "dev-01.pdf").read_bytes()


def test_display_name_is_sanitized(client, settings):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf", name="../../evil<x>.pdf").json()
    assert doc["file_name"] == "evil_x_.pdf"
    assert all(p.parent == settings.upload_dir for p in settings.upload_dir.iterdir())


def test_deliberate_error_needs_review_and_approval_rules(client):
    doc = upload(client, DEV / "pdf" / "dev-05.pdf").json()  # injection + total error
    assert doc["status"] == "needs_review"
    assert {f["code"] for f in doc["flags"]} == {"TOTAL_MISMATCH"}
    approve = client.post(f"/api/documents/{doc['id']}/approve", json={})
    assert approve.status_code == 409 and error(approve) == "OPEN_FLAGS"

    approved = client.post(
        f"/api/documents/{doc['id']}/approve", json={"acknowledge_open_flags": True}
    ).json()
    assert approved["status"] == "approved" and approved["acknowledged_open_flags"]
    locked = client.patch(
        f"/api/documents/{doc['id']}/fields",
        json={"changes": [{"field_path": "total", "value": "1,00 EUR"}]},
    )
    assert locked.status_code == 409 and error(locked) == "DOCUMENT_LOCKED"
    again = client.post(f"/api/documents/{doc['id']}/approve", json={})
    assert error(again) == "ALREADY_APPROVED"


def test_ambiguous_currency_is_flagged(client):
    doc = upload(client, DEV / "pdf" / "dev-03.pdf").json()  # "$" only
    assert doc["status"] == "needs_review"
    assert [(f["field_path"], f["code"]) for f in doc["flags"]] == [
        ("currency", "CURRENCY_AMBIGUOUS")
    ]


def test_invented_value_gets_a_grounding_flag(client, model):
    model.overrides["dev-01"] = {"vendor_name": "Evil Corp"}
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    assert doc["status"] == "needs_review"
    assert [(f["field_path"], f["code"]) for f in doc["flags"]] == [
        ("vendor_name", "VALUE_NOT_IN_DOCUMENT")
    ]


# --- corrections --------------------------------------------------------------


def test_patch_writes_audit_trail_and_revalidates(client):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    url = f"/api/documents/{doc['id']}"
    changed = client.patch(
        f"{url}/fields", json={"changes": [{"field_path": "total", "value": "$35,000.00"}]}
    ).json()
    assert changed["status"] == "needs_review"
    assert ("total", "TOTAL_MISMATCH") in {(f["field_path"], f["code"]) for f in changed["flags"]}
    assert not any(f["code"] == "VALUE_NOT_IN_DOCUMENT" for f in changed["flags"])

    fixed = client.patch(
        f"{url}/fields", json={"changes": [{"field_path": "total", "value": "$35,292.69"}]}
    ).json()
    assert fixed["status"] == "extracted" and fixed["flags"] == []
    trail = client.get(f"{url}/corrections").json()["corrections"]
    assert [(c["original_value"], c["corrected_value"]) for c in trail] == [
        ("$35,292.69", "$35,000.00"),
        ("$35,000.00", "$35,292.69"),
    ]
    assert all(c["field_path"] == "total" and c["created_at"] for c in trail)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"changes": [{"field_path": "nope", "value": "1"}]}, "UNKNOWN_FIELD"),
        ({"changes": [{"field_path": "total", "value": "1", "extra": 1}]}, "VALIDATION_ERROR"),
        ({"changes": []}, "NO_CHANGES"),
        ({}, "VALIDATION_ERROR"),
    ],
)
def test_bad_patches(client, body, code):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    response = client.patch(f"/api/documents/{doc['id']}/fields", json=body)
    assert response.status_code == 422 and error(response) == code


# --- duplicates, failures, retry ----------------------------------------------


def test_duplicate_upload_is_409_with_existing_id(client):
    first = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    second = upload(client, DEV / "pdf" / "dev-01.pdf", name="copy.pdf")
    assert second.status_code == 409 and error(second) == "DUPLICATE"
    assert second.json()["error"]["document_id"] == first["id"]
    assert len(client.get("/api/documents").json()["documents"]) == 1


def test_failed_extraction_duplicate_and_retry(client, model):
    model.failures["dev-01"] = LLMError(LLMErrorCode.UNAVAILABLE, "503 high demand")
    failed = upload(client, DEV / "pdf" / "dev-01.pdf")
    assert failed.status_code == 201
    doc = failed.json()
    assert doc["status"] == "failed" and doc["retry_available"]
    assert doc["error"] == {"code": "LLM_UNAVAILABLE", "message": "503 high demand"}
    assert error(client.post(f"/api/documents/{doc['id']}/approve", json={})) == "NOT_APPROVABLE"

    duplicate = upload(client, DEV / "pdf" / "dev-01.pdf")
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == doc["id"] and duplicate.json()["retry_available"]

    del model.failures["dev-01"]
    retried = client.post(f"/api/documents/{doc['id']}/retry").json()
    assert retried["status"] == "extracted" and retried["error"] is None
    assert error(client.post(f"/api/documents/{doc['id']}/retry")) == "RETRY_NOT_ALLOWED"


def test_missing_api_key_gives_a_failed_document(settings, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini = settings.model_copy(update={"llm_provider": "gemini", "gemini_api_key": None})
    app = create_app(gemini)  # real provider factory; fails before any network use
    with TestClient(app) as client:
        doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    app.state.services.engine.dispose()
    assert doc["status"] == "failed" and doc["error"]["code"] == "LLM_NOT_CONFIGURED"


def test_status_filter(client, model):
    model.failures["dev-02"] = LLMError(LLMErrorCode.TIMEOUT, "slow")
    upload(client, DEV / "pdf" / "dev-01.pdf")
    upload(client, DEV / "pdf" / "dev-02.pdf")
    failed = client.get("/api/documents", params={"status": "failed"}).json()["documents"]
    assert [d["status"] for d in failed] == ["failed"]
    bad = client.get("/api/documents", params={"status": "weird"})
    assert bad.status_code == 422 and error(bad) == "INVALID_STATUS"


def test_delete_removes_row_and_file(client, settings):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert list(settings.upload_dir.iterdir()) == []


# --- export -------------------------------------------------------------------


def test_export_contains_approved_documents_only(client, model):
    model.failures["dev-02"] = LLMError(LLMErrorCode.UNAVAILABLE, "503")
    approved = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    client.post(f"/api/documents/{approved['id']}/approve", json={})
    upload(client, DEV / "pdf" / "dev-04.pdf")  # extracted, not approved
    upload(client, DEV / "pdf" / "dev-02.pdf")  # failed

    exported = client.get("/api/export", params={"format": "json"}).json()["documents"]
    assert [d["document_id"] for d in exported] == [approved["id"]]
    assert exported[0]["total"] == "35292.69" and len(exported[0]["line_items"]) == 6

    response = client.get("/api/export", params={"format": "csv"})
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 6  # one row per line item
    assert {r["document_id"] for r in rows} == {approved["id"]}
    assert [r["line_number"] for r in rows] == ["1", "2", "3", "4", "5", "6"]
    assert rows[0]["description"] == "Cable management kit" and rows[0]["amount"] == "9448.25"


def test_empty_export(client):
    assert client.get("/api/export").json() == {"documents": []}
    assert client.get("/api/export", params={"format": "csv"}).text.count("\n") == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=HYPERLINK(1)", "'=HYPERLINK(1)"),
        ("+1", "'+1"),
        ("@x", "'@x"),
        ("-x", "'-x"),
        ("-12.50", "-12.50"),
        ("Acme", "Acme"),
        (None, ""),
    ],
)
def test_csv_formula_guard(value, expected):
    assert safe_cell(value) == expected


# --- upload validation --------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content_type", "data", "status", "code"),
    [
        ("a.txt", "application/pdf", b"%PDF-1.4 x", 415, "NOT_A_PDF"),
        ("a.pdf", "text/plain", b"%PDF-1.4 x", 415, "NOT_A_PDF"),
        ("a.pdf", "application/pdf", b"MZ\x90\x00 not a pdf", 415, "NOT_A_PDF"),
        ("a.pdf", "application/pdf", b"", 415, "NOT_A_PDF"),
        ("a.pdf", "application/pdf", b"%PDF-" + b"0" * (2**20 + 10), 413, "FILE_TOO_LARGE"),
        ("a.pdf", "application/pdf", b"%PDF-1.4\nnot really\n", 422, "INVALID_PDF"),
    ],
)
def test_upload_validation(client, settings, model, name, content_type, data, status, code):
    response = upload(client, None, name=name, content_type=content_type, data=data)
    assert response.status_code == status and error(response) == code
    assert list(settings.upload_dir.iterdir()) == []  # nothing left behind
    assert model.seen == []


@pytest.mark.parametrize(
    ("make", "code"),
    [(image_only_pdf, "SCANNED_PDF_UNSUPPORTED"), (encrypted_pdf, "ENCRYPTED_PDF")],
)
def test_unsupported_pdfs_are_rejected(client, settings, tmp_path, make, code):
    response = upload(client, make(tmp_path / "x.pdf"))
    assert response.status_code == 422 and error(response) == code
    assert list(settings.upload_dir.iterdir()) == []
    assert client.get("/api/documents").json()["documents"] == []


# --- test-set guard -----------------------------------------------------------


def test_real_test_set_pdf_is_refused_before_extraction(client, settings, model):
    response = upload(client, TEST_PDF)
    assert response.status_code == 403 and error(response) == "TEST_SET_DOCUMENT"
    assert model.seen == [] and model.calls == []  # never sent to the model
    assert list(settings.upload_dir.iterdir()) == []
    assert client.get("/api/documents").json()["documents"] == []


def test_test_set_uploads_need_the_explicit_setting(settings, model, monkeypatch):
    """Simulated with a dev file marked as test-set, so no test PDF is extracted."""
    monkeypatch.setattr(api, "is_test_set_sha256", lambda digest: True)
    assert Settings(_env_file=None).allow_test_set_uploads is False  # default off
    with TestClient(create_app(settings, provider=model)) as client:
        assert error(upload(client, DEV / "pdf" / "dev-01.pdf")) == "TEST_SET_DOCUMENT"
    allowed = settings.model_copy(update={"allow_test_set_uploads": True})
    app = create_app(allowed, provider=model)
    with TestClient(app) as client:
        assert upload(client, DEV / "pdf" / "dev-01.pdf").status_code == 201
    app.state.services.engine.dispose()


# --- error shape --------------------------------------------------------------


def test_errors_share_one_shape(client):
    assert error(client.get("/api/documents/nope")) == "NOT_FOUND"
    assert error(client.get("/api/documents/" + "x" * 300)) == "NOT_FOUND"
    assert error(client.get("/api/unknown")) == "NOT_FOUND"
    assert error(client.delete("/api/export")) == "METHOD_NOT_ALLOWED"
    assert error(client.get("/api/export", params={"format": "xml"})) == "VALIDATION_ERROR"
    assert error(client.post("/api/documents")) == "VALIDATION_ERROR"  # no file


# --- CORS (for the Vite dev server) -------------------------------------------


def test_cors_allows_the_configured_dev_origin_only(client):
    origin = "http://localhost:5173"
    preflight = client.options(
        "/api/documents/abc/fields",
        headers={"Origin": origin, "Access-Control-Request-Method": "PATCH"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "PATCH" in preflight.headers["access-control-allow-methods"]
    simple = client.get("/api/health", headers={"Origin": origin})
    assert simple.headers["access-control-allow-origin"] == origin
    other = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_times_carry_a_utc_offset_after_a_database_round_trip(client):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    client.post(f"/api/documents/{doc['id']}/approve")
    again = client.get(f"/api/documents/{doc['id']}").json()  # fresh session: naive in SQLite
    for key in ("created_at", "updated_at", "approved_at"):
        assert again[key].endswith("+00:00"), key
    exported = client.get("/api/export?format=json").json()["documents"][0]
    assert exported["approved_at"].endswith("+00:00")


# --- error paths found by the coverage review (Phase 6) -----------------------


def test_declared_size_over_the_limit_is_refused_before_reading(client, settings):
    big = b"%PDF-" + b"0" * (2**20 + 200 * 1024)  # over 1 MB + one 64 KiB chunk
    response = upload(client, DEV / "pdf" / "dev-01.pdf", data=big)
    assert response.status_code == 413 and error(response) == "FILE_TOO_LARGE"
    assert not settings.upload_dir.exists() or not any(settings.upload_dir.iterdir())


def test_missing_stored_pdf_is_404_file_missing(client, settings):
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    (settings.upload_dir / f"{doc['id']}.pdf").unlink()
    response = client.get(f"/api/documents/{doc['id']}/pdf")
    assert response.status_code == 404 and error(response) == "FILE_MISSING"


def test_retry_of_an_unreadable_stored_pdf_is_rejected_and_stays_failed(client, model, settings):
    model.failures["dev-01"] = LLMError(LLMErrorCode.UNAVAILABLE, "503")
    doc = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    (settings.upload_dir / f"{doc['id']}.pdf").write_bytes(b"%PDF-1.4 broken")
    response = client.post(f"/api/documents/{doc['id']}/retry")
    assert response.status_code == 422 and error(response) == "INVALID_PDF"
    assert client.get(f"/api/documents/{doc['id']}").json()["status"] == "failed"


def test_simultaneous_duplicate_upload_is_409_and_leaves_no_file(client, settings, monkeypatch):
    first = upload(client, DEV / "pdf" / "dev-01.pdf").json()
    # Simulate the race: the duplicate check runs before the first row is visible.
    monkeypatch.setattr(api.DocumentRepository, "get_by_sha256", lambda self, sha256: None)
    second = upload(client, DEV / "pdf" / "dev-01.pdf")
    assert second.status_code == 409 and error(second) == "DUPLICATE"
    assert [p.name for p in settings.upload_dir.iterdir()] == [f"{first['id']}.pdf"]
    assert len(client.get("/api/documents").json()["documents"]) == 1
