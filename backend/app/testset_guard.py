"""Keep manual runs off the frozen test set.

A PDF counts as a test-set document if it lies under eval/datasets/test, or if
its SHA-256 matches a file in the test manifest (so a copy elsewhere is caught
too). Only the Phase 7 evaluation passes ``allow_test_set=True``.
"""

import hashlib
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_SET_DIR = REPO_ROOT / "eval" / "datasets" / "test"


class TestSetGuardError(Exception):
    __test__ = False  # not a pytest test class


@cache
def _manifest_hashes(test_dir: Path) -> frozenset[str]:
    manifest = test_dir / "MANIFEST.sha256"
    if not manifest.is_file():  # e.g. a Docker image without the datasets
        return frozenset()
    lines = manifest.read_text(encoding="utf-8").splitlines()
    return frozenset(line.split("  ", 1)[0] for line in lines if line.strip())


def is_test_set_file(path: Path, test_dir: Path = TEST_SET_DIR) -> bool:
    resolved = path.resolve()
    if resolved.is_relative_to(test_dir.resolve()):
        return True
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return digest in _manifest_hashes(test_dir.resolve())


def guard_test_set(path: Path, allow_test_set: bool, test_dir: Path = TEST_SET_DIR) -> None:
    if is_test_set_file(path, test_dir) and not allow_test_set:
        raise TestSetGuardError(
            f"{path} is part of the frozen test set. Manual runs use eval/datasets/dev only; "
            "the Phase 7 evaluation passes --allow-test-set."
        )
