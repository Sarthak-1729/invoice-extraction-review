"""Evaluation sets and their integrity checks.

Each set is a folder with ``pdf/``, ``truth/`` and ``MANIFEST.sha256`` (the
SHA-256 of every file). The set's hash is the SHA-256 of the manifest file.
Before any use the manifest hash must equal the recorded hash, and every file
must match the manifest exactly (none edited, added or removed).

- ``dev``: tuning set (10 documents).
- ``test``: frozen held-out set (24 documents); hash logged in
  eval/TESTSET_CHANGELOG.md.
- ``handmade``: optional hand-made set in eval/handmade/, run separately. Its
  hash is the latest "Handmade-set hash" line in eval/handmade/CHANGELOG.md.
  It does not exist until someone adds documents.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
DATASETS = EVAL_DIR / "datasets"
HANDMADE_DIR = EVAL_DIR / "handmade"

DEV_SHA256 = "1f670b801453a8e9f1fdad5bc56335a3e2fbf39668ef4c68f0a9d25565e7a4be"
TEST_SHA256 = "5584672000bc2df17eacdbc4e8c7f442e0f214ce1182f1f47b8fa8e55f005681"
_HANDMADE_HASH_LINE = re.compile(r"Handmade-set hash:\s*`?([0-9a-f]{64})`?")


class EvalSetError(Exception):
    pass


@dataclass(frozen=True)
class EvalSet:
    name: str
    directory: Path
    expected_sha256: str | None
    held_out: bool  # needs --allow-test-set

    @property
    def manifest(self) -> Path:
        return self.directory / "MANIFEST.sha256"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def handmade_expected_sha256(directory: Path = HANDMADE_DIR) -> str | None:
    changelog = directory / "CHANGELOG.md"
    if not changelog.is_file():
        return None
    hashes = _HANDMADE_HASH_LINE.findall(changelog.read_text(encoding="utf-8"))
    return hashes[-1] if hashes else None


def get_set(name: str) -> EvalSet:
    if name == "dev":
        return EvalSet("dev", DATASETS / "dev", DEV_SHA256, held_out=False)
    if name == "test":
        return EvalSet("test", DATASETS / "test", TEST_SHA256, held_out=True)
    if name == "handmade":
        return EvalSet("handmade", HANDMADE_DIR, handmade_expected_sha256(), held_out=True)
    raise EvalSetError(f"Unknown set {name!r}; use dev, test or handmade.")


def read_manifest(eval_set: EvalSet) -> dict[str, str]:
    if not eval_set.manifest.is_file():
        raise EvalSetError(f"{eval_set.name}: no manifest at {eval_set.manifest}.")
    entries = {}
    for line in eval_set.manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            entries[name] = digest
    return entries


def verify(eval_set: EvalSet) -> str:
    """Check the manifest hash and every file; return the set hash."""
    if eval_set.expected_sha256 is None:
        raise EvalSetError(
            f"{eval_set.name}: no recorded hash. For the hand-made set, add the documents, "
            "write MANIFEST.sha256 and log its hash in eval/handmade/CHANGELOG.md first."
        )
    entries = read_manifest(eval_set)
    actual_hash = _sha256(eval_set.manifest)
    if actual_hash != eval_set.expected_sha256:
        raise EvalSetError(
            f"{eval_set.name}: manifest hash {actual_hash} does not match the recorded "
            f"{eval_set.expected_sha256}. The set changed; do not run."
        )
    actual = {
        path.relative_to(eval_set.directory).as_posix(): _sha256(path)
        for sub in ("pdf", "truth")
        for path in (eval_set.directory / sub).rglob("*")
        if path.is_file()
    }
    if actual != entries:
        changed = sorted(set(actual.items()) ^ set(entries.items()))
        names = sorted({name for name, _ in changed})
        raise EvalSetError(f"{eval_set.name}: files differ from the manifest: {names[:10]}")
    return actual_hash


def document_ids(eval_set: EvalSet) -> list[str]:
    return sorted(Path(name).stem for name in read_manifest(eval_set) if name.startswith("pdf/"))


def pdf_path(eval_set: EvalSet, doc_id: str) -> Path:
    return eval_set.directory / "pdf" / f"{doc_id}.pdf"


def load_truth(eval_set: EvalSet, doc_id: str) -> dict[str, Any]:
    return json.loads((eval_set.directory / "truth" / f"{doc_id}.json").read_text("utf-8"))
