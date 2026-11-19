# Baseline record: test set, extraction_v4, gemini-3.5-flash-lite

Hand-written companion to the generated `report.md` (which is rebuilt from
`results.json` and not edited by hand). Everything here comes from the saved
files in this folder and the frozen test PDFs' text layers, read locally. No
API call, no rerun and no prompt change was made for this record.

## Run

| | |
|---|---|
| Git commit | `f451523bbb2d664dd7262c60828ba3016d605018` (clean tree) |
| Prompt | extraction_v4, `852b70c465cb48cf452a552d3214b5206e1d9153c3ee2ac8a91ffb52174b0c2c` |
| Model | gemini-3.5-flash-lite (thinking level unset, 16384 output tokens, 3 transient retries) |
| Test-set hash | `5584672000bc2df17eacdbc4e8c7f442e0f214ce1182f1f47b8fa8e55f005681` |
| Metric definitions | v1.1 |
| Runs | 1 (2026-11-18 12:45 to 12:51 UTC); no infrastructure or model failures |
| Coverage | 24 of 24 documents scored |

Accepted as the baseline as reported (METRICS section 8). It is not rerun.

## Headline (from results.json)

- Layer 2 decided accuracy 94.4% (1548/1640), 4 ambiguous excluded; strict
  94.2% (1548/1644). Layer 1 82.1% (1349/1644).
- Every one of the 92 errors is a line-item description (header fields: 0
  errors). Line items F1 74.2% (265/357 lines fully right, 357/357 matched).
- Flag recall 0.0% (0/92). Flag precision undefined (0/0): no flag landed on
  an error field and there were no false alarms. 22 accurate fields carried
  only explained flags (deliberate arithmetic errors, document ambiguity).

## Pieces the generated report does not explain

### Ambiguity: 4 fields, all handled, 0 induced

| Document | Field | Printed | Flag | Why it is ambiguous |
|---|---|---|---|---|
| test-02 | currency | `$` | CURRENCY_AMBIGUOUS | `$` alone stands for several currencies |
| test-17 | currency | `$` | CURRENCY_AMBIGUOUS | same |
| test-22 | invoice_date | `10/04/2026` | DATE_AMBIGUOUS | day and month both 12 or less |
| test-22 | due_date | `11/03/2026` | DATE_AMBIGUOUS | same |

The model copied all four exactly (layer 1 correct). The oracle run (the
normalizer on the truth's printed strings) is ambiguous on the same four
fields, so all 4 are document ambiguity and 0 are induced by the extraction.
These are the only problems in test-02, test-17 and test-22: the 3 documents
"whose only problems are ambiguous fields". A reviewer resolves each with
one flagged field (test-22: two).

### 0 of 92 errors flagged: grounding cannot see misplaced values

All 92 errors are `<item code> <correct description>` (confirmed row by row
in `error_notes.md`). The grounding check asks only whether the extracted
string occurs in the PDF text. These strings occur verbatim, because the
code is printed right before the description on the same text line, so the
check passes them. No other check looks at descriptions: arithmetic uses the
numbers (all 357 quantities, unit prices and amounts are correct at layer 2),
and the format checks do not apply to free text. So recall on these errors
is 0 of 92, and the unflagged errors per document are 3.83 (92/24), all in 3
documents (test-19: 43, test-20: 42, test-24: 7).

### Layer 1 versus layer 2

The 295 layer-1 differences are the 92 descriptions plus 203 amounts on 7
documents (test-05, 09, 10, 12, 13, 16, 21) where the model dropped a
currency-code prefix, for example `USD 5,995.65` -> `5,995.65` (also CHF,
EUR, `Rs.`, INR, CAD). All 203 are correct at layer 2, because the currency
field is extracted separately and the numbers are exact.

## Item codes: why dev-09 and test-22 worked and test-19, 20, 24 did not

### What the files show

| Document | Set | Item-column header | Rows that wrap | Where the code is in the text layer | v4 descriptions |
|---|---|---|---|---|---|
| dev-09 | dev | `Item Description Qty Unit Price Amount` | 22 of 43 | wrapped rows: on the middle line, after the description's first line; other rows: first token of the row's line | 43 of 43 right (dev run, PROMPT_LOG) |
| test-22 | test | same | 19 of 37 | same as dev-09 | 37 of 37 right |
| test-19 | test | same | 0 of 43 | first token of every row's line | 0 of 43 right |
| test-20 | test | `Item Description Amount Qty Unit Price` | 0 of 42 | first token of every row's line | 0 of 42 right |
| test-24 | test | `Item Description Qty Unit Price Amount` | 0 of 38 | first token of every row's line | 31 of 38 right (page 1: 31 of 31; page 2: 0 of 7) |

Text layer excerpts (`app.pdf_text`, the exact text the model received):

```
dev-09   Item Description Qty Unit Price Amount
         Laser toner cartridge #3743, matte black
         C396-82 finish, wall-mount bracket included, 23 $121.24 $2,788.52
         two-year limited warranty
         C282-70 Network switch, 8-port #4901 13 $215.75 $2,804.75

test-19  Item Description Qty Unit Price Amount
         A599-19 Standing desk frame #5085 11 $203.22 $2,235.42
         C366-20 Webcam 1080p #6196 15 $290.09 $4,351.35
```

### Proven from the files

1. The code column has the same header, `Item`, in all five documents (the
   generator's multipage layout labels it so; only test-20's column order
   differs). The header text does not distinguish the good from the bad
   documents.
2. The only layout difference between the two groups is wrapping:
   `wrap_descriptions` is true for dev-09 and test-22 and false for test-19,
   20 and 24 (generator configs in the truth files).
3. The row's own text does not decide the outcome. test-22's 18 unwrapped
   rows have exactly the shape of test-19's rows (code first on the line),
   and all 18 were extracted without the code.
4. test-24 fails exactly at the page break: 31 of 31 rows right on page 1,
   0 of 7 on page 2, with the same row format and header on both pages.
5. The dev set's only document with an item-code column is dev-09, and it
   wraps. The v4 rule ("If the table has a separate column for an item code,
   SKU, or part number, the code in that column is not part of the
   description") was accepted on dev-09 alone; the dev set had no
   unwrapped item-code table to test it on.

### Likely, but a guess (one run, no view into the model)

- In a wrapped table the description visibly starts on a line without the
  code, which shows that the code is a separate column; the model then
  applies the v4 rule to every row of that document, wrapped or not. Without
  wrapped rows, `Item Description` followed by `A599-19 Standing desk frame`
  reads like a single "Item Description" column whose values begin with a
  code. This fits all five documents but is not proven: proving it would
  need controlled runs on edited documents, which this record does not do
  (and must not do on the test set).
- `Item` is a common header for the description column itself, while the
  rule speaks of "an item code, SKU, or part number"; the word may not have
  been read as a code column. Plausible contributor, untested.
- test-24's switch at the page break is unexplained. Possibilities: the
  repeated header and running header on page 2 reset the model's reading of
  the table, or plain run-to-run variability (seen before on dev, see the
  README). One run cannot tell these apart.
