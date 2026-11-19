# Invoice Extraction with Human Review

Upload text-based PDF invoices, extract structured fields with an LLM, validate
them with Pydantic, flag risky fields with deterministic checks, and review,
correct and approve the result before exporting it.

> Work in progress. The full README (architecture, setup, screenshots and
> measured results) is written in a later phase. See [docs/DESIGN.md](docs/DESIGN.md)
> for the design.

## Run locally (development)

**Python 3.11 only.** `backend/pyproject.toml` requires `>=3.11,<3.12` and
CI uses 3.11.9 (`backend/.python-version`), so pip refuses to install into
any other Python. On Windows, `py` may default to a newer Python, so name
the version when you create the virtual environment (from `backend/`):

```
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Start the backend (from `backend/`):

```
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Review UI (from `frontend/`, Node 22.13+ or 24; CI uses 24.12.0 from
`frontend/.nvmrc`):

```
npm ci
npm run dev
```

Open http://localhost:5173. The UI calls the API at `VITE_API_URL`
(default `http://localhost:8000`; see `frontend/.env.example`). The API
accepts browser requests from the origins in `CORS_ORIGINS` (default: the
Vite dev server).

## Tests

No test calls a real LLM or needs an API key. Backend tests use the fake
provider with the network blocked; frontend tests inject a fake `api`
object into `App` and block `fetch`.

```
cd backend
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest --cov --cov-fail-under=96
cd ..
backend\.venv\Scripts\python.exe -m pytest eval
cd frontend
npm run lint
npm test
npm run build
```

CI (`.github/workflows/ci.yml`) runs the same steps on every push and pull
request, plus a check that the frozen test-set hash has not changed.

**ESLint is pinned to 9.39.5**, which ESLint has marked as no longer
supported (npm prints a deprecation warning). It stays on 9 because
`eslint-plugin-jsx-a11y` 6.10.2 does not yet declare support for ESLint 10;
the accessibility lint rules matter more here than the newer ESLint.

## Limitations

- **Synthetic data from one generator.** The dev and test sets come from the
  same generator (`eval/generator/`), so every reported number describes 24
  synthetic test invoices in these four layouts, not real-world invoices. The
  baseline (`eval/results/test/`) says nothing about other layouts, fonts or
  scanned documents.
- **Prices are random.** Unit prices are drawn from a range per currency, so
  some are unrealistic (for example an office chair at CAD 7.98). The
  arithmetic is always internally consistent, which is what the metrics rely on.
- **Text-based PDFs only.** Scanned PDFs (no text layer) are rejected; there is
  no OCR.
- **Item codes in descriptions are not detected.** The grounding check only
  confirms that an extracted value occurs in the PDF text, so a value copied
  from the wrong place passes. Measured on the test-set baseline: 92 of 357
  line-item descriptions came back as `<item code> <description>` (test-19:
  43 of 43, test-20: 42 of 42, test-24: 7 of 38), and 0 of the 92 were
  flagged. These were the only errors in the run. The two item-code tables
  whose descriptions wrap (dev-09 and test-22) were extracted correctly; the
  three that do not wrap were not. See
  `eval/results/test/.../baseline.md`.
- **Single runs vary.** The model's output is not fully repeatable: on one dev
  document the currency symbols on amounts were dropped in one run and kept
  in the next, with no relevant prompt change. Reported numbers therefore
  come from one specified run (model, prompt hash, git commit and date are
  recorded with every result), not from the best of several runs.
- **Prompt example matches the generator's reference format.** The active
  prompt tells the model to keep reference numbers "such as #1234" in
  descriptions, which is exactly the format the generator puts in every
  synthetic description. It was written to fix a dev document, but it also
  suits the test set (same generator), so the measured description accuracy
  (265 of 357 right) may be overstated compared with real invoices, whose
  references look different.
- **Fonts.** The generator uses the built-in Helvetica/Courier fonts, which have
  no `₹` glyph, so INR amounts are printed with `Rs.`.
