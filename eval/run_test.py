"""Run the extraction pipeline on an evaluation set (docs/METRICS.md v1.1).

Run from the repo root with the backend venv (Python 3.11):

    backend\\.venv\\Scripts\\python.exe -m eval.run_test --allow-test-set
    backend\\.venv\\Scripts\\python.exe -m eval.run_test --allow-test-set --next-run

Safety:
- The held-out sets (test, handmade) need --allow-test-set.
- The set's manifest hash and every file are verified before anything runs.
- The git tree must be clean (changes under eval/results/ are ignored, since
  this runner writes there). --allow-dirty overrides and records the dirty
  flag and the changed files in the results.
- Only the Gemini provider with the expected model (default
  gemini-3.5-flash-lite) and the active prompt are accepted.

Results go to eval/results/<set>/<model>__<prompt version>__<prompt hash>/:
- run.json: metadata (model, settings, prompt, git commit and dirty flag,
  set hash, metric version) and every run session.
- predictions.jsonl: one line per document attempt, appended as soon as the
  document finishes.

Runs (METRICS section 2a):
- Rerunning the same command resumes the current run: only documents with no
  answer yet are attempted. Finished documents are never redone.
- A document that failed for infrastructure reasons (429, 5xx, timeout) is
  re-attempted only in a later run: pass --next-run, at least 30 minutes after
  the previous run ended, up to 3 runs in total. Successes and model failures
  are never re-run.
- The run stops when a 429 survives the in-run retries (quota) and on
  configuration errors (bad key, missing model). Rerun to resume.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings
from app.eval_compare import (
    CONFIGURATION_ERROR,
    INFRASTRUCTURE_FAILURE,
    METRICS_VERSION,
    MODEL_FAILURE,
    failure_class,
)
from app.llm import LLMError, get_provider
from app.llm.base import LLMErrorCode, LLMProvider
from app.pdf_text import PdfRejected
from app.pipeline import run_pipeline
from app.prompt import load_prompt
from app.testset_guard import guard_test_set
from eval.sets import REPO_ROOT, EvalSet, EvalSetError, document_ids, get_set, pdf_path, verify

RESULTS_ROOT = REPO_ROOT / "eval" / "results"
RESULTS_PATHSPEC = "eval/results"
EXPECTED_MODEL = "gemini-3.5-flash-lite"
MAX_RUNS = 3  # N = 3 (METRICS 2a)
MIN_GAP = timedelta(minutes=30)
SUCCESS = "success"
EXIT_OK, EXIT_REFUSED, EXIT_STOPPED = 0, 2, 3


class RunRefused(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


# --- git ----------------------------------------------------------------------


class Git:
    """The few git facts the runner needs. Tests pass a fake."""

    def __init__(self, root: Path = REPO_ROOT) -> None:
        self.root = root

    def _run(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True
        ).stdout

    def head(self) -> str:
        return self._run("rev-parse", "HEAD").strip()

    def dirty_files(self) -> list[str]:
        """Changed or untracked files, ignoring the runner's own output folder."""
        out = self._run(
            "status", "--porcelain", "--untracked-files=all", "--", ".",
            f":(exclude){RESULTS_PATHSPEC}",
        )  # fmt: skip
        return [line[3:] for line in out.splitlines() if line.strip()]

    def changed_since(self, commit: str) -> list[str]:
        return self._run("diff", "--name-only", f"{commit}..HEAD").split()


# --- storage ------------------------------------------------------------------


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_predictions(path: Path) -> list[dict[str, Any]]:
    """All attempt records in order. A torn last line (crash while writing) is
    cut off so the next append starts on a clean line."""
    if not path.is_file():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
        path.write_bytes(data)
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def append_prediction(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        out.flush()


def latest_by_document(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[record["doc_id"]] = record
    return latest


def infra_runs(records: list[dict[str, Any]], doc_id: str) -> int:
    return len(
        {
            r["run_number"]
            for r in records
            if r["doc_id"] == doc_id and r["outcome"] == INFRASTRUCTURE_FAILURE
        }
    )


# --- run ----------------------------------------------------------------------


def run_settings(settings: Settings) -> dict[str, Any]:
    return {
        "gemini_thinking_level": settings.gemini_thinking_level,
        "gemini_max_output_tokens": settings.gemini_max_output_tokens,
        "gemini_timeout_seconds": settings.gemini_timeout_seconds,
        "gemini_min_interval_seconds": settings.gemini_min_interval_seconds,
        "llm_transient_retries": settings.llm_transient_retries,
        "llm_max_backoff_seconds": settings.llm_max_backoff_seconds,
        "max_pages": settings.max_pages,
    }


def run_dir_for(results_root: Path, eval_set: EvalSet, model: str) -> Path:
    prompt = load_prompt()
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", model)
    return results_root / eval_set.name / f"{safe_model}__{prompt.version}__{prompt.sha256[:12]}"


@dataclass
class Options:
    allow_test_set: bool = False
    allow_dirty: bool = False
    next_run: bool = False


def _check_resume(meta: dict[str, Any], fresh: dict[str, Any], git: Git) -> None:
    for key in ("set", "set_sha256", "provider", "model", "prompt_version", "prompt_hash"):
        if meta[key] != fresh[key]:
            raise RunRefused(f"{key} changed ({meta[key]!r} -> {fresh[key]!r}); not the same run.")
    if meta["settings"] != fresh["settings"]:
        raise RunRefused(
            f"Settings changed: {meta['settings']} -> {fresh['settings']}. "
            "Every run must use the same settings."
        )
    if meta["git_commit"] != fresh["git_commit"]:
        outside = [
            name
            for name in git.changed_since(meta["git_commit"])
            if not name.startswith(RESULTS_PATHSPEC + "/")
        ]
        if outside:
            raise RunRefused(
                f"The code changed since this run started at {meta['git_commit'][:12]} "
                f"({', '.join(outside[:5])}). Runs must use the same commit."
            )


def _unfinished(run_entry: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    """Documents of this run with no answer from it yet (a configuration error
    is not an answer: the document is attempted again once fixed)."""
    answered = {
        r["doc_id"]
        for r in records
        if r["run_number"] == run_entry["run_number"] and r["outcome"] != CONFIGURATION_ERROR
    }
    return [d for d in run_entry["documents"] if d not in answered]


def _run_ended(run_entry: dict[str, Any]) -> datetime:
    sessions = run_entry["sessions"]
    stamp = run_entry.get("ended") or (sessions[-1].get("ended") or sessions[-1]["started"])
    return datetime.fromisoformat(stamp)


def _plan(
    meta: dict[str, Any],
    records: list[dict[str, Any]],
    ids: list[str],
    options: Options,
    now: Callable[[], datetime],
    echo: Callable[[str], None],
) -> tuple[list[str], int]:
    """Which documents to attempt, and in which run. Empty list: nothing to do."""
    if not meta["runs"]:
        if options.next_run:
            raise RunRefused("There is no run yet. Start run 1 without --next-run.")
        return ids, 1
    current = meta["runs"][-1]
    number = current["run_number"]
    unfinished = _unfinished(current, records)
    if unfinished:
        if options.next_run:
            raise RunRefused(
                f"Run {number} is not finished ({len(unfinished)} documents without an answer). "
                "Rerun without --next-run to resume it first."
            )
        return unfinished, number

    latest = latest_by_document(records)
    retryable = [
        d
        for d in ids
        if latest[d]["outcome"] == INFRASTRUCTURE_FAILURE and infra_runs(records, d) < MAX_RUNS
    ]
    if not retryable:
        echo("Nothing to do: every document has its final outcome. Run python -m eval.metrics.")
        return [], number
    ready = _run_ended(current) + MIN_GAP
    if not options.next_run:
        echo(
            f"Run {number} is finished. {len(retryable)} document(s) had infrastructure "
            f"failures: {', '.join(retryable)}. Retry them in run {number + 1} with "
            f"--next-run, not before {_iso(ready)} (UTC)."
        )
        return [], number
    if now() < ready:
        raise RunRefused(
            f"Run {number + 1} may start 30 minutes after run {number} ended, "
            f"not before {_iso(ready)} (UTC)."
        )
    return retryable, number + 1


def run_evaluation(
    eval_set: EvalSet,
    provider: LLMProvider,
    settings: Settings,
    options: Options,
    *,
    results_root: Path = RESULTS_ROOT,
    git: Git | None = None,
    now: Callable[[], datetime] = utcnow,
    echo: Callable[[str], None] = print,
) -> tuple[int, Path]:
    """One invocation: resume the current run or start the next one."""
    git = git or Git()
    if eval_set.held_out and not options.allow_test_set:
        raise RunRefused(
            f"The {eval_set.name} set is held out. Pass --allow-test-set to run it "
            "(only for the reported evaluation)."
        )
    set_sha256 = verify(eval_set)
    dirty = git.dirty_files()
    if dirty and not options.allow_dirty:
        raise RunRefused(
            "The git tree is not clean (outside eval/results/): "
            + ", ".join(dirty[:10])
            + ". Commit or stash first, or pass --allow-dirty to record the run as dirty."
        )

    prompt = load_prompt()
    fresh = {
        "set": eval_set.name,
        "set_sha256": set_sha256,
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": prompt.version,
        "prompt_hash": prompt.sha256,
        "settings": run_settings(settings),
        "metrics_version": METRICS_VERSION,
        "git_commit": git.head(),
        "git_dirty": bool(dirty),
        "dirty_files": dirty,
    }
    run_dir = run_dir_for(results_root, eval_set, provider.model)
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path, predictions_path = run_dir / "run.json", run_dir / "predictions.jsonl"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        _check_resume(meta, fresh, git)
        if dirty:
            meta["git_dirty"] = True
            meta["dirty_files"] = sorted(set(meta.get("dirty_files", [])) | set(dirty))
    else:
        meta = {**fresh, "created": _iso(now()), "runs": []}

    records = read_predictions(predictions_path)
    ids = document_ids(eval_set)
    work, run_number = _plan(meta, records, ids, options, now, echo)
    if not work:
        return EXIT_OK, run_dir

    if len(meta["runs"]) < run_number:
        meta["runs"].append({"run_number": run_number, "documents": work, "sessions": []})
    run_entry = meta["runs"][run_number - 1]
    session = {"started": _iso(now()), "ended": None, "stopped": None, "git_commit": git.head()}
    run_entry["sessions"].append(session)
    _write_json(meta_path, meta)
    echo(f"Run {run_number}: {len(work)} document(s) to attempt. Results: {run_dir}")

    exit_code = EXIT_OK
    for doc_id in work:
        record = _attempt(eval_set, doc_id, provider, settings, run_number, now)
        if record["error_code"] == LLMErrorCode.BAD_REQUEST:
            answered = any(r["outcome"] == SUCCESS for r in records)
            if answered:  # METRICS 2a exception: other documents work with these settings
                record["outcome"] = MODEL_FAILURE
                record["note"] = "LLM_BAD_REQUEST while other documents succeeded"
        records.append(record)
        append_prediction(predictions_path, record)
        echo(
            f"{doc_id}: {record['outcome']}"
            + (f" ({record['error_code']})" if record["error_code"] else "")
        )
        if record["outcome"] == CONFIGURATION_ERROR:
            session["stopped"] = f"configuration error {record['error_code']}"
            echo(f"Stopping: configuration error {record['error_code']}. Fix it and rerun.")
            exit_code = EXIT_STOPPED
            break
        if record["error_code"] == LLMErrorCode.RATE_LIMITED:
            session["stopped"] = "rate limit or quota (429)"
            echo("Stopping: rate limit or quota reached (429). Rerun later to resume.")
            exit_code = EXIT_STOPPED
            break

    session["ended"] = _iso(now())
    run_entry["ended"] = session["ended"]
    _write_json(meta_path, meta)
    left = _unfinished(run_entry, records)
    echo(
        f"Run {run_number}: "
        + ("all documents attempted." if not left else f"{len(left)} document(s) still to do.")
    )
    return exit_code, run_dir


def _attempt(
    eval_set: EvalSet,
    doc_id: str,
    provider: LLMProvider,
    settings: Settings,
    run_number: int,
    now: Callable[[], datetime],
) -> dict[str, Any]:
    pdf = pdf_path(eval_set, doc_id)
    guard_test_set(pdf, allow_test_set=True)  # only reached after --allow-test-set
    started = now()
    note = ""
    try:
        result = run_pipeline(pdf, provider, settings).to_dict()
        code = (result.get("error") or {}).get("code")
        outcome = failure_class(code) or SUCCESS
    except PdfRejected as error:
        result = {"error": {"code": error.code, "message": error.message}}
        code, outcome = error.code, MODEL_FAILURE
    except Exception as error:  # recorded, retried in a later run
        result = {"error": {"code": "UNEXPECTED_ERROR", "message": repr(error)}}
        code, outcome = "UNEXPECTED_ERROR", INFRASTRUCTURE_FAILURE
        note = "unexpected exception"
    return {
        "doc_id": doc_id,
        "run_number": run_number,
        "started": _iso(started),
        "finished": _iso(now()),
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "outcome": outcome,
        "error_code": code,
        "note": note,
        "result": result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run_test",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--set", default="test", choices=["test", "handmade"])
    parser.add_argument("--allow-test-set", action="store_true", help="required for held-out sets")
    parser.add_argument("--allow-dirty", action="store_true", help="run on a dirty tree (recorded)")
    parser.add_argument("--next-run", action="store_true", help="start the next run (2 or 3)")
    parser.add_argument("--expect-model", default=EXPECTED_MODEL, metavar="MODEL")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        settings = Settings()
        if settings.llm_provider != "gemini":
            raise RunRefused(
                f"LLM_PROVIDER is {settings.llm_provider!r}; the evaluation uses gemini."
            )
        if settings.gemini_model != args.expect_model:
            raise RunRefused(
                f"GEMINI_MODEL is {settings.gemini_model!r}, expected {args.expect_model!r}."
            )
        eval_set = get_set(args.set)
        if eval_set.held_out and not args.allow_test_set:  # before building the provider
            raise RunRefused(f"The {eval_set.name} set is held out. Pass --allow-test-set.")
        provider = get_provider(settings)
        code, run_dir = run_evaluation(
            eval_set,
            provider,
            settings,
            Options(args.allow_test_set, args.allow_dirty, args.next_run),
        )
    except (RunRefused, EvalSetError) as error:
        print(f"Refused: {error}")
        return EXIT_REFUSED
    except LLMError as error:
        print(f"{error.code}: {error.message}")
        return EXIT_REFUSED
    print(f"Next: python -m eval.metrics {run_dir.relative_to(REPO_ROOT).as_posix()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
