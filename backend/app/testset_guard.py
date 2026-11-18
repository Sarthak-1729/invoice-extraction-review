"""Keep manual runs off the held-out evaluation sets.

The held-out sets are the frozen test set (eval/datasets/test) and the
optional hand-made set (eval/handmade). A PDF counts as held out if it lies
under one of those folders, or if its SHA-256 matches a file in one of their
manifests (so a copy elsewhere is caught too). Only the evaluation runner
passes ``allow_test_set=True``.
"""

import hashlib
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_SET_DIR = REPO_ROOT / "eval" / "datasets" / "test"
HANDMADE_DIR = REPO_ROOT / "eval" / "handmade"
HELD_OUT_DIRS = (TEST_SET_DIR, HANDMADE_DIR)


class TestSetGuardError(Exception):
    __test__ = False  # not a pytest test class


@cache
def _manifest_hashes(test_dir: Path) -> frozenset[str]:
    manifest = test_dir / "MANIFEST.sha256"
    if not manifest.is_file():  # e.g. a Docker image without the datasets
        return frozenset()
    lines = manifest.read_text(encoding="utf-8").splitlines()
    return frozenset(line.split("  ", 1)[0] for line in lines if line.strip())


def _dirs(test_dir: Path | None) -> tuple[Path, ...]:
    return HELD_OUT_DIRS if test_dir is None else (test_dir,)


def is_test_set_sha256(digest: str, test_dir: Path | None = None) -> bool:
    return any(digest in _manifest_hashes(d.resolve()) for d in _dirs(test_dir))


def is_test_set_file(path: Path, test_dir: Path | None = None) -> bool:
    resolved = path.resolve()
    if any(resolved.is_relative_to(d.resolve()) for d in _dirs(test_dir)):
        return True
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return is_test_set_sha256(digest, test_dir)


def guard_test_set(path: Path, allow_test_set: bool, test_dir: Path | None = None) -> None:
    if is_test_set_file(path, test_dir) and not allow_test_set:
        raise TestSetGuardError(
            f"{path} is part of a held-out evaluation set (test or hand-made). Manual runs "
            "use eval/datasets/dev only; the evaluation runner passes --allow-test-set."
        )
