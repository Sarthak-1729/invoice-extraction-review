"""Guard the frozen test set. Run from the repo root: python -m pytest eval/tests

If this fails, the test set changed. Do not update the hash to make it pass:
log the change and its reason in eval/TESTSET_CHANGELOG.md first.
"""

import hashlib
from pathlib import Path

import pytest

DATASETS = Path(__file__).resolve().parents[1] / "datasets"
FROZEN_TEST_SHA256 = "5584672000bc2df17eacdbc4e8c7f442e0f214ce1182f1f47b8fa8e55f005681"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_test_set_hash_matches_changelog():
    assert _sha256(DATASETS / "test" / "MANIFEST.sha256") == FROZEN_TEST_SHA256
    assert FROZEN_TEST_SHA256 in (DATASETS.parent / "TESTSET_CHANGELOG.md").read_text("utf-8")


@pytest.mark.parametrize("split", ["dev", "test"])
def test_files_match_manifest_exactly(split):
    split_dir = DATASETS / split
    expected = {}
    for line in (split_dir / "MANIFEST.sha256").read_text("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    actual = {
        path.relative_to(split_dir).as_posix(): _sha256(path)
        for path in split_dir.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
    }
    assert actual == expected  # no file edited, added or removed
