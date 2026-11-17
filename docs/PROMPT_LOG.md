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
- First full dev run, `python -m app.dev_check` (2026-11-17, git commit
  `39bc8bd`, clean tree, `gemini-3.5-flash-lite`, thinking level model
  default, prompt hash `83601bc5...34ea`). **Tuning-set results on the 10 dev
  documents, never test results.** Results:
  `data/dev_check/gemini__gemini-3.5-flash-lite__extraction_v2__83601bc5d5b7/`
  (git-ignored). Analysis from the saved result files only.

  | Doc | Status | Layer 1 | Layer 2 | Lines matched / truth (extra) | Flags | Tokens in / out |
  |---|---|---|---|---|---|---|
  | dev-01 | extracted | 33/33 | 33/33 | 6/6 (0) | none | 962 / 486 |
  | dev-02 | needs_review | 25/25 | 25/25 | 4/4 (0) | LINE_AMOUNT_MISMATCH (expected) | 917 / 397 |
  | dev-03 | needs_review | 23/41 | 40/41 | 8/8 (0) | CURRENCY_AMBIGUOUS | 942 / 551 |
  | dev-04 | extracted | 37/37 | 37/37 | 7/7 (0) | none | 1141 / 550 |
  | dev-05 | needs_review | 37/37 | 37/37 | 7/7 (0) | TOTAL_MISMATCH (expected) | 1214 / 570 |
  | dev-06 | needs_review | 12/21 | 21/21 | 3/3 (0) | SUBTOTAL_MISMATCH (expected) | 1061 / 317 |
  | dev-07 | extracted | 22/41 | 41/41 | 8/8 (0) | none | 1088 / 649 |
  | dev-08 | extracted | 41/41 | 41/41 | 8/8 (0) | none | 937 / 585 |
  | dev-09 | extracted | 138/181 | 138/181 | 43/43 (0) | none | 2817 / 3364 |
  | dev-10 | extracted | 193/193 | 193/193 | 46/46 (0) | none | 2157 / 3066 |

  - All 10 documents succeeded on the first attempt: 0 infrastructure
    failures, 0 model failures. All three expected arithmetic flags fired;
    no unexpected flags.
  - Totals: layer 1 561 of 650 fields; layer 2 606 of 650 (1 ambiguous);
    140 of 140 lines matched, 0 extra.
  - Layer 1 misses outside dev-09 (46 fields): the model dropped the
    attached currency marker from amounts: `$` on dev-03 (18), `CHF` on
    dev-06 (9), `Rs.` on dev-07 (19). All 46 are correct at layer 2.
  - dev-03 currency is `ambiguous` (`$`-only document): correct behavior.
  - dev-09: all 43 descriptions are wrong (layer 1 and 2) because each
    contains the line's item code from the SKU column: prefixed on the 21
    unwrapped lines, inserted at the wrap point on the 22 wrapped lines. All
    138 other dev-09 fields are correct. All 43 codes occur in the PDF text
    layer, in the same order, one per line, so they were copied, not
    invented. The SKU column header is printed as "Item", so the text layer
    reads `Item Description Qty Unit Price Amount`.
  - dev-10 (no SKU column) has no codes in its text layer or its output.
  - Split configs (not test results): 4 test documents have a SKU column
    (test-19, test-20, test-22, test-24), against 1 dev document (dev-09).

## Pre-registered acceptance criteria (written 2026-11-17, before any change)

Each candidate is one change, judged on one full `dev_check` run of all 10
dev documents against the v2 run above. One run each; a regression is not
explained away by rerunning only the new version. If any document ends with
an infrastructure failure, it is retried per METRICS 2a before judging; if it
never succeeds, the candidate is not judged. The test set is not used.

### Candidate 1: item codes are not part of the description (extraction_v3)

Must improve (dev-09):
- descriptions containing an item code: from 43 of 43 to 0 of 43;
- dev-09 layer 2: at least 178 of 181 (at least 40 of 43 descriptions
  correct), and the other 138 fields still all correct;
- still 43 of 43 lines matched, 0 extra.

No other dev document may regress. For each of dev-01 to dev-08 and dev-10:
- layer 1 and layer 2 counts are at least the v2 counts in the table above;
- lines matched not fewer, extra lines not more;
- the same status and the same set of flag codes.

If accepted, the result is still reported as tuned on 1 dev document with a
SKU column (4 test documents have one); the SKU documents in the test set are
reported as a case study.

### Candidate 2: copy amounts with their attached currency marker (not implemented)

Judged only after candidate 1 is decided, against whichever prompt is current.
Must improve: layer 1 on the 46 amount fields of dev-03, dev-06 and dev-07
that dropped the marker (target: all 46). No dev document may regress on
layer 2, lines, status or flags, and no document's layer 1 may fall: in
particular dev-01, dev-02, dev-04, dev-05, dev-08, dev-09 and dev-10, whose
amounts are already copied exactly, must not gain markers that are not
printed next to the amount.

## extraction_v3 (prompt tuning on dev): FAILED, not used

- Date: 2026-11-17
- Hash: `2b62b7814afc6e0eaaa362604a4095ef68e0efd950304e27b8c9f8e4803b812d`
- Model and settings: as v2.
- Change (the only one): one sentence added to the `description` rule in
  `system.txt`: "If the table has an item code, SKU, or part-number column,
  that code is not part of the description: leave it out." `user.txt` and
  `schema.json` are byte-identical to v2.
- Reason: dev-09 (v2 dev run above), where every description included the
  item code from the SKU column. Candidate 1 of the pre-registered criteria;
  tuned on 1 dev document. No test-set document was opened or run.
- Dev-set result: **rejected** under the pre-registered candidate 1 criteria.
  Tuning-set results, never test results. One `dev_check` run of all 10 dev
  documents (2026-11-17, git commit `10db3fd`, clean tree, all first attempt,
  no failures). Results:
  `data/dev_check/gemini__gemini-3.5-flash-lite__extraction_v3__2b62b7814afc/`
  (kept, not deleted). Analysis from the saved files only.

  | Doc | v2 layer 1 | v3 layer 1 | v2 layer 2 | v3 layer 2 | Lines (v3) | Status and flags |
  |---|---|---|---|---|---|---|
  | dev-01 | 33/33 | 33/33 | 33/33 | 33/33 | 6/6 | same |
  | dev-02 | 25/25 | 25/25 | 25/25 | 25/25 | 4/4 | same |
  | dev-03 | 23/41 | 41/41 | 40/41 | 40/41 | 8/8 | same |
  | dev-04 | 37/37 | 37/37 | 37/37 | 37/37 | 7/7 | same |
  | dev-05 | 37/37 | 37/37 | 37/37 | 37/37 | 7/7 | same |
  | dev-06 | 12/21 | 12/21 | 21/21 | 21/21 | 3/3 | same |
  | dev-07 | 22/41 | 22/41 | 41/41 | 41/41 | 8/8 | same |
  | dev-08 | 41/41 | 41/41 | 41/41 | 41/41 | 8/8 | same |
  | dev-09 | 138/181 | 181/181 | 138/181 | 181/181 | 43/43 | same |
  | dev-10 | 193/193 | **147/193** | 193/193 | **147/193** | 46/46 | same |

  - dev-09 criterion: **passed**. 181 of 181 at both layers, 43 of 43 lines,
    0 item codes in descriptions, all 43 `#NNNN` references kept.
  - No-regression criterion: **failed** on dev-10 (193 to 147 of 193). All 46
    differences are descriptions, each exactly the truth with its trailing
    ` #NNNN` reference removed. The reference is part of the description
    cell: the text layer reads for example `6 Monitor arm #3692 £444.37
    £2,666.22`, and all 46 truth descriptions end in `#NNNN`. dev-10 has no
    code column, so the model treated the reference itself as an "item code".
  - dev-03 layer 1 rose from 23 to 41 of 41 (the `$` signs were kept on the
    amounts this time). The change does not mention amounts or currency, so
    this is treated as run-to-run variation, not an effect of v3. With one run
    per version an indirect effect cannot be ruled out; it does not affect the
    decision.
  - Decision: v3 is not used. `extraction_v2` is the active prompt again
    (`PROMPT_VERSION`; a test pins it). The v3 files and hash are kept for the
    record.

## Pre-registered acceptance criteria for candidate v4 (written 2026-11-17, before v4 exists)

Candidate v4 targets the SKU problem again (dev-09) without v3's failure. It
is judged on one `dev_check` run of all 10 dev documents against the v2 run.
**One run, no reruns.** Infrastructure failures are handled per METRICS 2a;
if a document never succeeds, v4 is not judged.

Must pass all of:
- dev-09: layer 2 at least 178 of 181, 0 item codes in descriptions, 43 of
  43 lines matched, 0 extra lines.
- Every other dev document (dev-01 to dev-08, dev-10): layer 1 and layer 2 at
  least the v2 counts, lines matched not fewer, extra lines not more, the
  same status and the same set of flag codes.
- Exclusion: on dev-03, dev-06 and dev-07, layer 1 fields whose raw value
  equals the printed value with its attached currency marker removed are
  excluded from both the v2 and the v4 counts, because that behavior varied
  between runs with no relevant prompt change (v2 vs v3 on dev-03). Layer 2
  is compared without exclusions.

Stopping rule: if v4 fails, `extraction_v2` stays the active prompt, no
further SKU candidates are tried, and the SKU weakness is reported as a known
limitation (README), with the test documents that have a SKU column (test-19,
test-20, test-22, test-24) reported as a case study.

## extraction_v4 (prompt tuning on dev): ACCEPTED, active prompt

- Date: 2026-11-17
- Hash: `852b70c465cb48cf452a552d3214b5206e1d9153c3ee2ac8a91ffb52174b0c2c`
- Model and settings: as v2.
- Change (the only one, against v2, not v3): two sentences added to the
  `description` rule in `system.txt`: "If the table has a separate column for
  an item code, SKU, or part number, the code in that column is not part of
  the description. Text printed inside the description cell stays, including
  reference numbers such as "#1234"." `user.txt` and `schema.json` are
  byte-identical to v2.
- Reason: dev-09 (item codes in descriptions) without v3's failure on dev-10
  (references removed). The wording ties the exclusion to a separate column
  and says what stays.
- Known risk: the example "#1234" matches the reference format the generator
  puts in every description, in dev and test alike (same generator). If v4 is
  accepted, its effect on test documents may look better than it would on
  real invoices; the README limitation about the shared generator covers
  this, and the SKU documents are reported as a case study.
- Dev-set result: **accepted** under the pre-registered v4 criteria
  (commit `25e3bdb`). Tuning-set results, never test results. One
  `dev_check` run of all 10 dev documents, no reruns (2026-11-17, git commit
  `6af7f2e`, clean tree, all first attempt, no failures). Results:
  `data/dev_check/gemini__gemini-3.5-flash-lite__extraction_v4__852b70c465cb/`.
  Judged from the saved files only.

  | Doc | v2 layer 1 | v4 layer 1 | v2 layer 2 | v4 layer 2 | Lines v2 / v4 (extra) | Status and flags | Criterion |
  |---|---|---|---|---|---|---|---|
  | dev-01 | 33/33 | 33/33 | 33/33 | 33/33 | 6/6, 6/6 (0) | same | pass |
  | dev-02 | 25/25 | 25/25 | 25/25 | 25/25 | 4/4, 4/4 (0) | same | pass |
  | dev-03 | 23/23* | 23/23* | 40/41 | 40/41 | 8/8, 8/8 (0) | same | pass |
  | dev-04 | 37/37 | 37/37 | 37/37 | 37/37 | 7/7, 7/7 (0) | same | pass |
  | dev-05 | 37/37 | 37/37 | 37/37 | 37/37 | 7/7, 7/7 (0) | same | pass |
  | dev-06 | 12/12* | 12/12* | 21/21 | 21/21 | 3/3, 3/3 (0) | same | pass |
  | dev-07 | 22/22* | 22/22* | 41/41 | 41/41 | 8/8, 8/8 (0) | same | pass |
  | dev-08 | 41/41 | 41/41 | 41/41 | 41/41 | 8/8, 8/8 (0) | same | pass |
  | dev-09 | 138/181 | 181/181 | 138/181 | 181/181 | 43/43, 43/43 (0) | same | pass |
  | dev-10 | 193/193 | 193/193 | 193/193 | 193/193 | 46/46, 46/46 (0) | same | pass |

  \* Layer 1 after the pre-registered exclusion of fields that differ only
  by the attached currency marker (dev-03: 18, dev-06: 9, dev-07: 19 fields,
  the same fields in both runs). Without the exclusion the counts are also
  identical: dev-03 23/41, dev-06 12/21, dev-07 22/41 in both runs.

  - dev-09 criterion: **pass**. Layer 2 181 of 181 (needed at least 178),
    0 item codes in descriptions, 43 of 43 lines, 0 extra; all 43 `#NNNN`
    references kept.
  - No-regression criterion: **pass** for all nine other documents: layer 1
    and layer 2 equal to v2, same lines, status and flag codes. dev-10 is
    193 of 193 (v3 had 147).
  - Totals: layer 2 649 of 650 fields (the 1 is dev-03's `ambiguous` `$`
    currency, the correct outcome); layer 1 604 of 650 (the 46 misses are
    the dropped currency markers on dev-03, dev-06 and dev-07, unchanged
    from v2).
  - Decision: `extraction_v4` is the active prompt (`PROMPT_VERSION`, pinned
    by a test). This is tuned on one dev document with a SKU column; the four
    test documents with a SKU column (test-19, test-20, test-22, test-24) are
    reported as a case study, and the README notes that the "#1234" example
    matches the generator's reference format.
