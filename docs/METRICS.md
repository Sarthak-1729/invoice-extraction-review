# Evaluation metrics

Metric definitions version: **1.1**. Version 1 was written and committed before
any dataset was generated or any extraction was run; 1.1 adds the policy for
failed extractions (section 2a) and was also written before any test-set run.
Every results file records this version.
Changing a definition after results exist requires a new version number, a
changelog entry at the bottom with the reason, and recomputing every reported
run under both the old and the new version.

## 1. Units

- **Header fields (9 per document):** `invoice_number`, `vendor_name`,
  `bill_to_name`, `invoice_date`, `due_date`, `currency`, `subtotal`, `tax`,
  `total`.
- **Line-item fields (4 per line):** `description`, `quantity`, `unit_price`,
  `amount`.
- **Field instance:** one header field of one document, or one line-item field
  of one *matched* truth line (see section 5).
- Ground truth for each field has a canonical `value` and the exact `printed`
  string (`eval/datasets/<split>/truth/*.json`). For documents with deliberate
  arithmetic errors the truth is what is printed: the document is wrong, not the
  extraction.

## 2. Outcomes per field

Each field instance gets exactly one outcome:

| Outcome | Truth | Prediction |
|---|---|---|
| `correct` | value | equal value (rules below) |
| `correct_absent` | null | null |
| `wrong` | value | different value |
| `missing` | value | null |
| `hallucinated` | null | any value |
| `ambiguous` | value | layer 2 only: normalizer returned null with an `*_AMBIGUOUS` flag |

"Accurate" means `correct` or `correct_absent`. `wrong`, `missing` and
`hallucinated` are errors and are reported separately as well as in total.

Documents whose extraction failed are handled by section 2a: model failures
count as `missing` fields; infrastructure failures are retried across runs and
reported by count, never scored as answers.

## 2a. Failed extractions

Every document ends a run in exactly one class:

| Class | Error codes | Treatment |
|---|---|---|
| Success | none | Scored normally. |
| Model failure | `SCHEMA_VALIDATION_FAILED` (after the one in-run retry), `LLM_OUTPUT_INCOMPLETE` | An extraction failure. Every field of the document is `missing` at both layers and every truth line is unmatched. Counted in all accuracy denominators. Not re-run. |
| Infrastructure failure | `LLM_UNAVAILABLE` (5xx, connection), `LLM_RATE_LIMITED` (429), `LLM_TIMEOUT`, `LLM_ERROR` (unclassified) | Not an answer, so neither right nor wrong. Re-attempted in later runs, up to **N = 3 runs** in total. A document that never succeeds is left out of accuracy denominators and listed by count and document ID as "never succeeded (infrastructure)". Never dropped silently. |
| Configuration error | `LLM_AUTH_FAILED`, `LLM_NOT_CONFIGURED`, `LLM_BAD_REQUEST` | The run is invalid and stops. Nothing from it is reported; fix the configuration and start again. Exception: if `LLM_BAD_REQUEST` hits only some documents while others succeed with the same settings, those documents are model failures, with the message recorded. |

Rules for the N = 3 runs:

- Within a run, the in-run retries already apply (first attempt plus
  `LLM_TRANSIENT_RETRIES` retries, honoring the server's retry delay).
- Runs 2 and 3 re-attempt **only** documents whose latest outcome is an
  infrastructure failure. Successes and model failures are never re-run, so
  no document is retried until its answer looks better.
- Runs 2 and 3 start at least 30 minutes after the previous run ended and use
  the same git commit, prompt hash, model and settings. Anything else is a new
  run, not a retry.
- The results file records, for each document, which run produced its
  outcome and every attempt's error code.

Why N = 3: the 503s seen on 2026-11-05 were temporary demand spikes ("high
demand ... usually temporary"). Three runs spread over at least an hour, each
with 4 attempts, give a document 12 attempts across different times, which
should outlast a spike, while capping the extra free-tier usage at 3x for a
document that keeps failing. A larger N mostly spends quota.

Every headline number states both counts next to it, for example:
`Layer 2 decided accuracy 95.0% (190/200 fields; 23 of 24 documents scored;
1 never succeeded (infrastructure); 1 extraction failure counted as missing)`.
When any document never succeeded, layer 2 strict accuracy is also given with
those documents counted as `missing` (the worst case).

## 3. Layer 1: raw extraction accuracy (printed string copied correctly)

Compares the model's `RawExtraction` string with the truth `printed` string.

- Both sides: Unicode NFKC, whitespace collapsed to single spaces, trimmed.
  Otherwise exact (case-sensitive, punctuation-sensitive). `1,234.50` and
  `1234.50` are different at this layer.
- Currency exception: a raw currency is also `correct` when it is a currency
  marker printed elsewhere in the same document that denotes the same ISO code
  (for example `$` on a document whose note says `All amounts in USD`). The
  number of currency fields scored correct this way is reported.
- The `ambiguous` outcome does not exist at this layer.

Layer 1 isolates the LLM: it says whether the model read and copied the
document correctly, independent of our normalization code.

## 4. Layer 2: end-to-end accuracy (normalized value correct)

The raw extraction goes through `app.normalize`; the normalized value is
compared with the truth `value`:

| Field type | Equality rule |
|---|---|
| `invoice_number` | NFKC, all whitespace removed, case-sensitive |
| `vendor_name`, `bill_to_name`, `description` | NFKC, whitespace collapsed, case-folded |
| dates | ISO date equality |
| `subtotal`, `tax`, `total`, `quantity`, `unit_price`, `amount` | Decimal numeric equality (`1234.5` == `1234.50`) |
| `currency` | ISO 4217 code equality |

### Ambiguous dates and `$`-only currencies

When the normalizer cannot decide (`DATE_AMBIGUOUS`, `CURRENCY_AMBIGUOUS`,
`NUMBER_FORMAT_AMBIGUOUS`), the normalized value is null and the outcome is
`ambiguous`. It is never silently counted right or wrong. Layer 2 accuracy is
reported two ways, always side by side:

- **Decided accuracy** = accurate / (all − ambiguous). Example:
  `95.0% (190/200), 6 ambiguous excluded`.
- **Strict accuracy** = accurate / all (ambiguous counted as not accurate).

Ambiguous fields are further split by cause, using an **oracle run**: the
normalizer applied to the truth `printed` strings (a perfect extractor):

- **Document ambiguity:** the oracle is also ambiguous for this field (for
  example a `$`-only invoice, or `03/04/2026` with no other date that fixes the
  order). Correct behavior is to flag, so these count as handled.
- **Induced ambiguity:** the oracle is not ambiguous, so the extraction created
  the ambiguity (for example the model dropped a decimal separator).

### Document-level accuracy

A document is correct when all 9 header fields are accurate at layer 2
(strict: `ambiguous` counts as not accurate). Reported as:

- **Header-only document accuracy.**
- **Full document accuracy:** header correct, and every truth line is matched
  with all 4 fields accurate, and there are no unmatched predicted lines.
- The number of documents whose only problems are `ambiguous` fields.

## 5. Line-item matching

Predicted lines are matched one-to-one to truth lines within each document:

1. Pairs whose layer-2-normalized descriptions are equal are matched first, in
   document order.
2. The remaining pairs are scored with `difflib.SequenceMatcher` ratio on the
   normalized descriptions. Pairs with ratio ≥ 0.6 are matched greedily, highest
   ratio first; ties are broken by truth line order, then predicted line order.
3. Everything left is unmatched: an unmatched predicted line is a false
   positive, an unmatched truth line is a false negative.

Greedy matching (not an optimal assignment) is used because descriptions in
this dataset are unique per document; this is a known simplification.

Metrics, micro-averaged over all lines of the split:

- **True positive line:** a matched pair with all 4 fields accurate at layer 2.
- **Precision** = TP / predicted lines. **Recall** = TP / truth lines.
  **F1** = harmonic mean. A matched pair with any wrong field counts as both a
  false positive and a false negative.
- **Match rate** (description matched, fields not checked) and **per-field
  accuracy over matched pairs** are reported separately.

## 6. Arithmetic validity rate

A document is arithmetically valid when `check_arithmetic` on its normalized
predicted invoice returns no arithmetic flags. Reported separately for:

- **Consistent documents** (truth `arithmetic_consistent: true`): validity rate.
- **Deliberately inconsistent documents:** case studies only (section 8): did
  the expected arithmetic flag fire on the expected fields?

## 7. Flagging effectiveness

Flags come only from deterministic checks; the LLM's confidence is never used.

- **Flagged field instance:** a flag's `field_path` names the field. A flag on
  the table path `line_items` (for example `SUBTOTAL_MISMATCH`) marks every
  line-item field instance of that document as flagged.
- **Error field:** layer 2 outcome `wrong`, `missing` or `hallucinated`.
  `ambiguous` fields are flagged by construction and are excluded from the
  precision and recall below (reported in section 4 instead).
- **Explained flag on an accurate field** (neither a hit nor a false alarm,
  reported separately):
  - an arithmetic flag on a document with a deliberate arithmetic error;
  - an `*_AMBIGUOUS` flag where the oracle run is also ambiguous.
- **False alarm:** any other flag on an accurate field.

Definitions:

- **Flag recall** = flagged error fields / error fields.
- **Flag precision** = flagged error fields / (flagged error fields + false alarms).
- **Missed errors per document** = unflagged error fields / documents.
- **Reviewer load:**
  - review items per document: distinct flagged paths, where the table path
    `line_items` counts as one item (mean and median);
  - flagged field instances per document (mean and median).
- **Reference points**, reported next to the system's numbers:
  - *no review*: load 0, recall 0;
  - *review every field*: load = all field instances, recall 100%.

## 8. Reporting rules

- **Counts next to every percentage:** `92.3% (36/39)`. No bare percentages.
- **Small groups (< 5 documents): case studies, not rates.** Each document is
  listed with what happened, and counts are given as `x of y fields`, with no
  percentage. This applies at least to: deliberate arithmetic errors (4 test
  documents), injection lines (2), wrapped descriptions (2), and any other
  slice under 5 documents.
- **Test-only features get their own breakdown:** JPY (3 documents), CAD (2),
  plain numbers (1) and `amount_before_qty` columns (2). All are under 5
  documents, so they are reported as case studies with field counts, next to
  the same counts for the rest of the test set.
- **Per-layout breakdowns** (6 test documents each) are reported with counts.
- **Per-field tables** list layer 1 and layer 2 side by side for each of the 13
  field types.
- **Run metadata** in every results file: provider, model, generation settings,
  prompt hash, git commit (and whether the tree was dirty), date, test-set hash
  from `MANIFEST.sha256`, and this metric definition version.
- **Baseline:** the first full test run is the baseline. Later runs are
  reported as before/after with the baseline kept, noting that tuning used the
  dev set only. No run is dropped or re-run selectively.

## 9. Error analysis causes

Every error field is assigned one primary cause:

| Cause | Rule |
|---|---|
| Extraction | layer 1 wrong and the truth printed string is contiguous in the PDF text |
| Layout / text order | layer 1 wrong and the truth string is split in the text layer (wrapped cell, page break) or sits next to a distractor (customer number, "Line total", page header) |
| Normalization | layer 1 correct, layer 2 wrong |
| Schema failure | the document failed schema validation |
| Grounding check | applies to flags, not values: a grounding flag on an accurate field, or an error the grounding check should have caught |
| Document inconsistency | not an error: deliberate arithmetic mismatch printed on the document |

Causes are assigned automatically where these rules decide, then confirmed by
hand in a notes file next to the results.

## Changelog

- v1: initial definitions.
- v1.1 (2026-11-16): added section 2a, the policy for failed extractions
  (model failures count as `missing`; infrastructure failures retried up to
  N = 3 runs and reported by count, not scored). Written before any test-set
  run; the only runs so far were 4 dev documents checked by hand.
