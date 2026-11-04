# Prompt log

Every change to the extraction prompt gets a new version directory under
`backend/app/prompts/` and an entry here, with its hash and its **dev-set**
result. The test set is never used for prompt work (see
`eval/TESTSET_CHANGELOG.md`); it is only run in Phase 7 evaluation runs.

The prompt hash is the SHA-256 over `system.txt`, `user.txt` and
`schema.json` (each followed by a zero byte), computed by `app/prompt.py`.
Print it with:

    cd backend
    .venv\Scripts\python.exe -c "from app.prompt import load_prompt; p = load_prompt(); print(p.version, p.sha256)"

Results below are copied from runs that were actually made, with the model,
settings and date. "Not run" means no result exists yet.

## extraction_v1

- Date: 2026-11-04
- Hash: `7e798ea6a3263b567f590a1488838e0a5249237dfeb1b26eab61f3840dcfe2b2`
- Model: `gemini-3.5-flash-lite` (thinking level: model default,
  `max_output_tokens` 16384)
- Design:
  - All rules live in the system prompt (security rules first, then
    extraction rules and field definitions).
  - The user message only labels the data block and wraps the PDF text in
    `<document_text>` tags; tag-like text inside the document is escaped.
  - Values are copied verbatim as printed; nulls instead of guesses; no
    computing totals, tax or due dates.
  - Hand-written flat response schema (`["string", "null"]` per field, no
    `anyOf`, `additionalProperties: false`, at most 500 line items).
- Dev-set result: not run.
