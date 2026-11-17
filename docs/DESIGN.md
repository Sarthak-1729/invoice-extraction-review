# Design

Approved plan (Phase 0) with later amendments. This file is the source of
truth for scope; changes are added to the changelog at the bottom.

## Goal

Upload text-based PDF invoices, extract structured fields with an LLM,
validate with Pydantic, flag risky fields with deterministic checks, and let a
human review, correct, approve and export the result. Scanned PDFs (no text
layer) are rejected with a clear message. Invoices only in v1.

## Stack

| Area | Choice | Reason |
|---|---|---|
| API | FastAPI, Python 3.11 | Typed, async-capable, OpenAPI docs for free |
| Validation | Pydantic v2 | Schema for LLM output, API and normalized data |
| PDF text | pdfplumber | Pure Python (pdfminer.six), Windows wheels, keeps table layout, per-page char counts for scanned-PDF detection |
| Storage | SQLite + SQLAlchemy 2.0 | DB models kept separate from API/LLM schemas |
| LLM | Gemini via `LLM_PROVIDER`, model from `GEMINI_MODEL` | Fake provider for tests; Ollama optional and labeled untested |
| Frontend | React + Vite (JS), plain CSS | Vitest + React Testing Library + vitest-axe |
| Tooling | ruff, ESLint + jsx-a11y, GitHub Actions, Docker | |
| Synthetic PDFs | reportlab with `invariant=1` | Byte-stable output, so file hashes are reproducible |

## Data model: two layers

1. **`RawExtraction`** is what the LLM returns: each value is the string as
   printed in the document, or null. Verbatim strings make the grounding
   check possible and keep number/date parsing out of the model.
2. **`Invoice`** is built by deterministic code (`app/normalize.py`):
   `date`, `Decimal` money (never float), ISO 4217 currency code. Each field
   keeps its raw string next to the normalized value.

Fields: `invoice_number, vendor_name, bill_to_name, invoice_date, due_date,
currency, subtotal, tax, total, line_items[] {description, quantity,
unit_price, amount}`.

Ambiguous values are flagged, never guessed. `03/04/2026` is resolved only
when another date in the same document fixes the day/month order.

## Storage

SQLite through SQLAlchemy 2.0 (`app/db.py`, `app/repository.py`). Tables:
`documents` (status, error code and message, raw and normalized values as
JSON, the PDF text for re-validation, prompt version and hash), `flags`
(recomputed on every validation) and `corrections` (append-only audit trail:
field path, original value, corrected value, timestamp). The schema is
created with `Base.metadata.create_all()` at startup; there is no migration
tool yet (Alembic is the path once real data needs a schema change). The
database file and uploaded PDFs live in git-ignored `data/` and `uploads/`.

## Flags

Each flag: `{field_path, code, severity: error|warning, message}`. Field paths
look like `total` or `line_items[2].amount`. The LLM's self-reported
confidence is never used.

| Signal | Codes |
|---|---|
| Arithmetic (tolerance: one minor unit of the currency) | `LINE_AMOUNT_MISMATCH`, `SUBTOTAL_MISMATCH`, `TOTAL_MISMATCH` |
| Grounding | `VALUE_NOT_IN_DOCUMENT` |
| Format | `DATE_UNPARSEABLE`, `DATE_AMBIGUOUS`, `AMOUNT_UNPARSEABLE`, `NUMBER_FORMAT_AMBIGUOUS`, `CURRENCY_UNKNOWN`, `CURRENCY_AMBIGUOUS` |
| Consistency | `DUE_BEFORE_INVOICE_DATE`, `REQUIRED_FIELD_MISSING`, `LINE_ITEMS_EMPTY` |
| Optional | `RUN_DISAGREEMENT` (off by default: doubles API usage) |
| Pipeline | `SCHEMA_VALIDATION_FAILED` (document level, after one retry) |

Arithmetic flags are attached to every field in the failing equation. A
subtotal mismatch flags `subtotal` and the line-item table as a whole
(`line_items`), not each line, so a 30-line invoice does not produce 31 flags.
When the subtotal is missing, the total is checked against the sum of lines.

## Statuses

`extracted` (no flags) -> `needs_review` (flags) -> `approved` (locked).
`failed` holds an `error_code` and `error_message` when extraction fails
(LLM error, invalid output after retry).

## API

Error shape: `{"error": {"code": "...", "message": "..."}}`.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `POST /api/documents` | Upload, extract, validate. 201. 413 `FILE_TOO_LARGE`, 415 `NOT_A_PDF`, 422 `SCANNED_PDF_UNSUPPORTED` / `ENCRYPTED_PDF` / `TOO_MANY_PAGES`. Duplicate: 409 `DUPLICATE` with the existing id, except a duplicate of a `failed` document returns that document with `retry_available: true` (200) |
| `GET /api/documents?status=` | List |
| `GET /api/documents/{id}` | Raw + normalized fields, flags, corrections, error |
| `GET /api/documents/{id}/pdf` | Stored file, looked up by id only |
| `POST /api/documents/{id}/retry` | Re-run extraction on the stored file (no re-upload). Allowed for `failed` |
| `DELETE /api/documents/{id}` | Delete document and stored file |
| `PATCH /api/documents/{id}/fields` | `{changes:[{field_path, value}]}`; writes audit trail, re-validates |
| `POST /api/documents/{id}/approve` | `{acknowledge_open_flags}`; 409 if flags are open and not acknowledged |
| `GET /api/documents/{id}/corrections` | Audit trail (original, corrected, timestamp) |
| `GET /api/export?format=json\|csv` | Approved documents only (never `failed`); CSV has one row per line item |

## Upload validation

Extension `.pdf`, declared content type, and `%PDF-` magic bytes must agree.
Size limit `MAX_UPLOAD_MB`, page limit `MAX_PAGES`, streamed to disk. SHA-256
for duplicate detection. Stored as `uploads/<uuid>.pdf`; the original name is
sanitized and used for display only.

## Prompt injection

Rules live only in the system prompt. PDF text is wrapped in
`<document_text>...</document_text>`, labeled as untrusted data, with any
closing tag inside it escaped. Every output is validated with Pydantic; the
grounding and arithmetic checks catch values the document does not support.

## UI

Landmarks, labels, full keyboard operation, `aria-live` status updates,
visible focus, no meaning by color alone, WCAG AA contrast. Failed documents
are listed with their error message and "Retry extraction" and "Delete"
buttons.

## Evaluation

- Ground truth JSON is written first (canonical values plus the exact
  rendered strings); the generator renders PDFs from it.
- Layouts are built one at a time, with 2-3 sample PDFs reviewed by hand after
  each. At least 4 layouts; varied date/currency formats, multi-page, varied
  table columns, missing optional fields, deliberate arithmetic errors,
  odd wording, prompt-injection lines. Names come from an invented word list.
- 10 dev documents (prompt tuning), 24 test documents (held out), different
  seeds. Dev and test come from the same generator, so results describe
  synthetic invoices; the README must say so.
- The test set, truth files and `MANIFEST.sha256` are committed and frozen
  before the first extraction run. CI recomputes the hash. Any later change is
  logged in `eval/TESTSET_CHANGELOG.md` with its reason. Every results file
  records the test-set hash.
- Runner: rate limit from env, retry with backoff on 429/503 (honoring
  Retry-After), progress saved after each document, resumable. Results record
  model, settings, prompt hash, git commit (+ dirty flag), date.
- Metrics (every percentage shown with its n): per-field and overall
  accuracy (normalized exact match; null vs null is correct, value vs null is
  a hallucination); document-level accuracy (header only, header + lines);
  line-item P/R/F1; arithmetic validity rate; flag recall and precision per
  field instance; fields to review per document; missed errors per document;
  reference points "no review" and "review every field".
- Small groups (deliberate arithmetic errors, injection lines) are reported
  as case studies with counts, not rates.
- Error analysis by cause: extraction, normalization, grounding check,
  layout/text order, schema failure, deliberate document inconsistency.
- The first full test run is the baseline. Later runs are reported
  before/after with the baseline kept, noting tuning used the dev set only.

## LLM model

`gemini-3.5-flash-lite` (set through `GEMINI_MODEL`). Checked on 2026-11-04:
the model page lists it as Stable with "Structured outputs: supported".
SDK: `google-genai` (the old `google-generativeai` is deprecated), Interactions
API `client.interactions.create` with a JSON-schema `response_format`, read
from `output_text`, sent with `store=False`. The SDK's built-in retries are
off; `app/extraction.py` owns retries. The docs do not publish free-tier
limits (they point to Google AI Studio), so pacing is configurable
(`GEMINI_MIN_INTERVAL_SECONDS`, default 6 s).

Provider error codes: `LLM_RATE_LIMITED` (429), `LLM_UNAVAILABLE` (5xx,
connection), `LLM_TIMEOUT` (timeouts, 408, 504), `LLM_AUTH_FAILED` (401, 403),
`LLM_BAD_REQUEST` (other 4xx), `LLM_NOT_CONFIGURED`, `LLM_OUTPUT_INCOMPLETE`,
`LLM_ERROR`, and `SCHEMA_VALIDATION_FAILED` after one retry. PDF rejections
add `INVALID_PDF` to the upload codes.

## Changelog

- Phase 0 approved. Amendments: `failed` status with error code/message;
  retry endpoint; duplicate of a failed document returns it with a retry
  option; failed documents excluded from export; UI retry/delete for failed
  documents; layout-by-layout generator review; counts next to percentages;
  small groups as case studies; README notes same-generator limitation;
  starting model `gemini-3.5-flash-lite` pending docs check.
- Phase 3: `gemini-3.5-flash-lite` confirmed (structured outputs supported).
  Schema failure after one retry is a `failed` extraction with
  `SCHEMA_VALIDATION_FAILED`. Added `INVALID_PDF`. Manual runs are blocked on
  the test set unless `--allow-test-set` is given (Phase 7).
- Phase 4: storage uses `create_all()` (no Alembic yet). Grounding is not
  applied to fields a reviewer corrected. Approval needs every open flag
  acknowledged. Uploads whose SHA-256 is in the test manifest are refused
  unless `ALLOW_TEST_SET_UPLOADS=true` (off by default; Phase 7 only).
- Phase 5: review UI in `frontend/` (Vite + React, plain CSS, hash routes
  `#/` and `#/documents/<id>`). `App` receives its `api` object as a prop.
  Edits are saved together with one "Save changes" button (one PATCH), not
  on every keystroke. Approving with open flags needs a confirmation
  checkbox. Line items can be edited but not added or removed (the PATCH
  API only addresses existing lines). Busy buttons use `aria-disabled` so
  keyboard focus is never lost. Backend: `CORS_ORIGINS` setting (Vite dev
  origins by default), and timestamps always carry a UTC offset (SQLite
  drops the time zone). LLM failures stay a saved `failed` document (201),
  not a 502, so the UI can offer Retry.
