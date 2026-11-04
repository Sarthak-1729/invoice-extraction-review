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
- **Fonts.** The generator uses the built-in Helvetica/Courier fonts, which have
  no `₹` glyph, so INR amounts are printed with `Rs.`.
