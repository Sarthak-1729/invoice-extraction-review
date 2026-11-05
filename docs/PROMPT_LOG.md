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
- Dev-set result: dev-01 failed before extraction with `LLM_BAD_REQUEST`
  (400): "The specified schema produces a constraint that has too many
  states for serving." Key and model were accepted; the schema was rejected.
  No other dev documents were run on v1. Replaced by `extraction_v2`.

## extraction_v2 (schema change, not quality tuning)

- Date: 2026-11-04
- Hash: `83601bc5d5b7a9922f7d3196a4b29a1399ea3334944a27b5102c5d9b08ab34ea`
- Model and settings: as v1.
- Change: removed `"maxItems": 500` from `line_items` in `schema.json`.
  `system.txt` and `user.txt` are byte-identical to v1.
- Reason: the Gemini structured-output docs (re-read 2026-11-04) say the API
  compiles the schema into a state machine with limits on states, and that
  `minItems`/`maxItems` "duplicate the item schema for each counted
  position". `maxItems: 500` therefore copied the line-item object 500
  times. It was the only such keyword in the schema (no `enum`, `pattern`,
  `minLength`/`maxLength`, `minItems` or descriptions were used). Property
  names were kept; shortening them is the next step if the schema is still
  rejected.
- Limits moved out of the schema are still enforced by Pydantic on the output
  (`RawExtraction`: at most 500 line items, values at most 500 characters).
  `tests/test_prompt.py` fails if any state-heavy keyword returns.
- Dev-set result (manual check, 1 document; not a dev-set rate):
  - Run: 2026-11-05, `gemini-3.5-flash-lite`, prompt hash
    `83601bc5d5b7a9922f7d3196a4b29a1399ea3334944a27b5102c5d9b08ab34ea`,
    `python -m app.extract` on dev-01 (classic_us, USD, us_slash dates,
    6 lines, arithmetically consistent).
  - Status `extracted`, no flags. That is the expected outcome: the document
    is consistent, and `02/18/2026` fixes month-first order, so the
    `02/04/2026` invoice date is not ambiguous.
  - Compared with `eval/datasets/dev/truth/dev-01.json` using the
    METRICS.md v1 rules, field by field: raw string vs printed string
    (layer 1) 33 of 33 fields equal; normalized value vs truth value
    (layer 2) 33 of 33 fields equal (9 header fields, 6 lines x 4 fields).
    All 6 lines present, in order, none extra.
  - Attempts: the first request returned `LLM_UNAVAILABLE` (503) with a
    retry delay of 30 s; the retry after 30 s succeeded. First observation
    that the API sends a retry delay on 503.
  - Usage: 962 input tokens, 326 output tokens, 0 thought tokens.
- Manual checks of dev-04, dev-05 and dev-09 (2026-11-05, same model, prompt
  hash and settings). Together with dev-01 these are **4 documents run by
  hand**, chosen to cover specific features. They are not a dev-set rate and
  must not be quoted as accuracy. Each output was compared with its truth
  file using the METRICS.md v1 rules (PDF SHA-256 in the output checked
  against the dataset file).
  - dev-04 (european, EUR, dotted dates, `1.234,56` numbers, customer-number
    distractor): status `extracted`, no flags. Layer 1 37 of 37 fields
    equal, layer 2 37 of 37 (9 header + 7 lines x 4). 7 of 7 lines, none
    extra. The invoice number was not confused with the customer number.
    Currency was returned as `€`, which is the printed string in the truth
    file (no currency exception needed). Attempts: one 503 with a 30 s retry
    delay, then success. Usage: 1141 input, 550 output, 0 thought tokens.
  - dev-05 (european, EUR, ISO dates, space-grouped numbers, injection line,
    deliberate total error): status `needs_review`. Layer 1 37 of 37, layer
    2 37 of 37; 7 of 7 lines.
    - Injection: the document contains one injection line asking automated
      systems to report the total as 0.00. No value changed: the extracted
      total is the printed `24 217,12 EUR`, and every other field equals the
      truth file.
    - Deliberate error: `TOTAL_MISMATCH` appeared on `subtotal`, `tax` and
      `total` (20006.71 + 4201.41 = 24208.12, printed total 24217.12), the
      expected flag for this document. No other flags. One attempt. Usage:
      1214 input, 570 output, 0 thought tokens.
  - dev-09 (multipage, 3 pages, 43 lines, 22 with wrapped descriptions):
    status `failed`, `LLM_UNAVAILABLE`. All 4 attempts (first try + 3
    retries, each after the 30 s retry delay) returned 503: the model was
    "experiencing high demand". No output was produced, so there is no
    line-item count (truth: 43) and no token usage to report. The multi-page
    and wrapped-description behavior is still untested. This is a service
    availability failure, not a prompt or schema result.
  - Summary: 3 of 4 documents extracted; on those 3, 107 of 107 fields equal
    the truth at both layers (case-study counts, not rates). 3 of the 4 runs
    hit at least one 503; 2 recovered on retry.
