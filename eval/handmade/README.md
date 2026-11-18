# Hand-made evaluation set (optional, empty)

A second held-out set made by hand, separate from the generated dev and test
sets, so that results are not only about one generator's invoices. It is run
separately and reported separately. **It contains no documents yet.**

Rules:

- Synthetic documents only. No real invoices and no real personal or company
  data. Invent every name, address and number.
- Text-based PDFs only (no scans).
- Never used for prompt tuning. Uploading or running these PDFs is refused
  without the explicit flag, exactly like the test set.

Layout, the same as `eval/datasets/<split>/`:

```
eval/handmade/
  pdf/<id>.pdf
  truth/<id>.json        same format as eval/datasets/test/truth/*.json
  MANIFEST.sha256        "<sha256>  pdf/<id>.pdf" for every pdf and truth file
  CHANGELOG.md           the set hash, one entry per version
```

Truth files use the generator's format (`schema_version`, `doc_id`, `layout`,
`features`, `arithmetic_consistent`, `fields` with `value` and `printed` for
the 9 header fields, `line_items` with the 4 line fields). Use feature names
from the generated sets where they apply (for example `currency:JPY`,
`sku_column`, `wrapped_descriptions`, `injection`, `arith_error:total`), so
the same breakdowns work.

To freeze the set:

1. Add `pdf/` and `truth/`, then write the manifest (from `eval/handmade/`,
   in Git Bash): `sha256sum pdf/* truth/* > MANIFEST.sha256`
2. Hash the manifest: `sha256sum MANIFEST.sha256`
3. Add an entry to `CHANGELOG.md` with the line
   ``Handmade-set hash: `<that hash>` `` and commit everything together.

Run it (after the test-set evaluation, never mixed with it):

```
backend\.venv\Scripts\python.exe -m eval.run_test --set handmade --allow-test-set
```
