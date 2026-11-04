# Test-set changelog

The test set (`eval/datasets/test/`) is frozen. Its hash is the SHA-256 of
`eval/datasets/test/MANIFEST.sha256`, which lists the SHA-256 of every PDF and
truth file. Every results file records this hash.

Rules: the test set is never edited after results have been seen, unless the
change is logged here with the reason and a new hash, and every earlier run is
reported against the hash it used. `eval/tests/test_testset_frozen.py` fails if
the files drift from the manifest or the manifest drifts from the hash below.

Verify:

    cd eval/datasets/test && sha256sum -c MANIFEST.sha256 && sha256sum MANIFEST.sha256

## Entries

### 2026-11-04: v1, frozen before any extraction run

- Test-set hash: `5584672000bc2df17eacdbc4e8c7f442e0f214ce1182f1f47b8fa8e55f005681`
- 24 documents (seeds 2001-2024), 30 pages, 48 files.
- Generated with `python -m eval.generator.generate split test`.
- Dev set at the same time (not frozen; used for tuning):
  `1f670b801453a8e9f1fdad5bc56335a3e2fbf39668ef4c68f0a9d25565e7a4be`
  (10 documents, 13 pages).
