# Invoice Extraction with Human Review

Upload text-based PDF invoices, extract structured fields with an LLM, validate
them with Pydantic, flag risky fields with deterministic checks, and review,
correct and approve the result before exporting it.

> Work in progress. The full README (architecture, setup, screenshots and
> measured results) is written in a later phase. See [docs/DESIGN.md](docs/DESIGN.md)
> for the design.

## Limitations

- **Synthetic data only.** The dev and test sets come from the same generator
  (`eval/generator/`), so evaluation results describe synthetic invoices with
  these four layouts, not real-world invoices.
- **Prices are random.** Unit prices are drawn from a range per currency, so
  some are unrealistic (for example an office chair at CAD 7.98). The
  arithmetic is always internally consistent, which is what the metrics rely on.
- **Text-based PDFs only.** Scanned PDFs (no text layer) are rejected; there is
  no OCR.
- **Grounding catches invented values, not misplaced ones.** The grounding
  check confirms that an extracted value occurs in the PDF text. A value
  copied from the wrong place still passes: for example an item code from a
  SKU column copied into the description (seen on a dev document) is in the
  text, so it is not flagged.
- **Single runs vary.** The model's output is not fully repeatable: on one dev
  document the currency symbols on amounts were dropped in one run and kept
  in the next, with no relevant prompt change. Reported numbers therefore
  come from one specified run (model, prompt hash, git commit and date are
  recorded with every result), not from the best of several runs.
- **Prompt example matches the generator.** The active prompt tells the model
  to keep reference numbers "such as #1234" in descriptions, which is exactly
  the format the generator puts in every synthetic description. It was
  written to fix a dev document, but it also suits the test set (same
  generator), so test-set description accuracy may be overstated compared
  with real invoices, whose references look different.
- **Fonts.** The generator uses the built-in Helvetica/Courier fonts, which have
  no `₹` glyph, so INR amounts are printed with `Rs.`.
