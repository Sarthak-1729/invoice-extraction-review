"""The guard covers both held-out sets: the frozen test set and the hand-made set."""

import hashlib

import pytest

from app import testset_guard
from app.testset_guard import TestSetGuardError, guard_test_set, is_test_set_sha256


@pytest.fixture
def held_out(tmp_path, monkeypatch):
    test_dir, handmade_dir = tmp_path / "test", tmp_path / "handmade"
    for folder, content in ((test_dir, b"%PDF-test"), (handmade_dir, b"%PDF-handmade")):
        (folder / "pdf").mkdir(parents=True)
        (folder / "pdf" / "a.pdf").write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        (folder / "MANIFEST.sha256").write_text(f"{digest}  pdf/a.pdf\n", encoding="utf-8")
    monkeypatch.setattr(testset_guard, "HELD_OUT_DIRS", (test_dir, handmade_dir))
    return test_dir, handmade_dir


def test_hand_made_pdfs_are_guarded_by_path_and_by_hash(held_out, tmp_path):
    _, handmade_dir = held_out
    with pytest.raises(TestSetGuardError, match="held-out"):
        guard_test_set(handmade_dir / "pdf" / "a.pdf", allow_test_set=False)
    copy = tmp_path / "elsewhere.pdf"
    copy.write_bytes(b"%PDF-handmade")
    with pytest.raises(TestSetGuardError):
        guard_test_set(copy, allow_test_set=False)
    assert is_test_set_sha256(hashlib.sha256(b"%PDF-handmade").hexdigest())
    guard_test_set(copy, allow_test_set=True)  # the evaluation runner


def test_other_files_pass(held_out, tmp_path):
    other = tmp_path / "dev.pdf"
    other.write_bytes(b"%PDF-dev")
    guard_test_set(other, allow_test_set=False)
    assert not is_test_set_sha256(hashlib.sha256(b"%PDF-dev").hexdigest())


def test_real_hand_made_folder_has_no_documents_yet():
    assert not (testset_guard.HANDMADE_DIR / "MANIFEST.sha256").exists()
    assert not (testset_guard.HANDMADE_DIR / "pdf").exists()
