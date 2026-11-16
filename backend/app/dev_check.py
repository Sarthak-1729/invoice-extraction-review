"""Run the 10 dev documents and compare them with their truth files.

Run from backend/ with the venv active:
    python -m app.dev_check                 # all dev documents not done yet
    python -m app.dev_check --only dev-09   # selected dev documents

Dev set only: the documents come from eval/datasets/dev/pdf (checked against
the dev manifest), every path also passes the test-set guard, and there is no
option to point it anywhere else.

Results go to data/dev_check/<provider>__<model>__<prompt version>__<hash>/
(git-ignored): one JSON file per document, written as soon as it finishes, and
report.md. Rerunning resumes: successes and model failures are skipped;
infrastructure failures are retried, up to 3 runs per document (METRICS 2a).
The run stops at the first sign of quota exhaustion (a 429 that survived the
retries, or a retry delay too long to wait) and on configuration errors.

This is a development aid. Its counts are not reported metrics.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.eval_compare import (
    CONFIGURATION_ERROR,
    INFRASTRUCTURE_FAILURE,
    METRICS_VERSION,
    MODEL_FAILURE,
    DocComparison,
    compare_document,
    failure_class,
)
from app.llm import LLMError, get_provider
from app.llm.base import LLMErrorCode, LLMProvider
from app.pdf_text import PdfRejected, extract_text
from app.pipeline import run_pipeline
from app.prompt import load_prompt
from app.testset_guard import REPO_ROOT, guard_test_set

DEV_DIR = REPO_ROOT / "eval" / "datasets" / "dev"
RESULTS_ROOT = REPO_ROOT / "data" / "dev_check"  # git-ignored (data/)
MAX_INFRA_RUNS = 3  # METRICS.md section 2a, N = 3

EXIT_OK, EXIT_STOPPED_QUOTA, EXIT_CONFIG = 0, 3, 2


class DevCheckError(Exception):
    pass


def _dev_manifest() -> dict[str, str]:
    lines = (DEV_DIR / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (line.split("  ", 1) for line in lines if line)}


def dev_documents(only: list[str] | None = None) -> list[Path]:
    pdfs = sorted((DEV_DIR / "pdf").glob("dev-*.pdf"))
    if only:
        known = {pdf.stem for pdf in pdfs}
        unknown = sorted(set(only) - known)
        if unknown:
            raise DevCheckError(f"Not dev documents: {', '.join(unknown)}. Known: {sorted(known)}")
        pdfs = [pdf for pdf in pdfs if pdf.stem in set(only)]
    manifest = _dev_manifest()
    for pdf in pdfs:
        guard_test_set(pdf, allow_test_set=False)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if manifest.get(f"pdf/{pdf.name}") != digest:
            raise DevCheckError(f"{pdf.name} does not match the dev manifest.")
    return pdfs


def run_dir_for(out_root: Path, provider: LLMProvider) -> Path:
    prompt = load_prompt()
    model = re.sub(r"[^A-Za-z0-9._-]", "_", provider.model)
    return out_root / f"{provider.name}__{model}__{prompt.version}__{prompt.sha256[:12]}"


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_metadata(provider: LLMProvider, settings: Settings) -> dict[str, Any]:
    prompt = load_prompt()
    status = _git("status", "--porcelain")
    return {
        "provider": provider.name,
        "model": provider.model,
        "prompt_version": prompt.version,
        "prompt_hash": prompt.sha256,
        "metrics_version": METRICS_VERSION,
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "settings": {
            "gemini_thinking_level": settings.gemini_thinking_level,
            "gemini_max_output_tokens": settings.gemini_max_output_tokens,
            "gemini_min_interval_seconds": settings.gemini_min_interval_seconds,
            "llm_transient_retries": settings.llm_transient_retries,
        },
    }


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)  # never leaves a half-written result


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def should_run(previous: dict[str, Any] | None, retry_infra: bool) -> tuple[bool, str]:
    if previous is None:
        return True, "new"
    outcome = previous.get("outcome")
    if outcome in ("success", MODEL_FAILURE):
        return False, f"done ({outcome})"
    if outcome == INFRASTRUCTURE_FAILURE:
        runs = previous.get("infra_runs", 0)
        if runs >= MAX_INFRA_RUNS and not retry_infra:
            return False, f"never succeeded after {runs} runs (infrastructure)"
        return True, f"retry after {runs} infrastructure failure(s)"
    return True, f"retry ({outcome})"


def run_documents(
    settings: Settings,
    provider: LLMProvider,
    out_root: Path = RESULTS_ROOT,
    only: list[str] | None = None,
    retry_infra: bool = False,
    echo: Callable[[str], None] = print,
) -> tuple[int, Path]:
    """Run the dev documents that are not done; returns (exit code, run dir)."""
    pdfs = dev_documents(only)
    run_dir = run_dir_for(out_root, provider)
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = run_metadata(provider, settings)

    for pdf in pdfs:
        path = run_dir / f"{pdf.stem}.json"
        previous = _load(path)
        go, reason = should_run(previous, retry_infra)
        if not go:
            echo(f"{pdf.stem}: skip, {reason}")
            continue
        echo(f"{pdf.stem}: running ({reason})")
        started = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            result = run_pipeline(pdf, provider, settings).to_dict()
            code = (result.get("error") or {}).get("code")
            outcome = failure_class(code) or "success"
        except PdfRejected as error:
            result = {"error": {"code": error.code, "message": error.message}}
            code, outcome = error.code, MODEL_FAILURE
        except Exception as error:  # keep going; recorded and retried next run
            result = {"error": {"code": "UNEXPECTED_ERROR", "message": repr(error)}}
            code, outcome = "UNEXPECTED_ERROR", INFRASTRUCTURE_FAILURE

        history = (previous or {}).get("history", [])
        record = {
            "doc_id": pdf.stem,
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "outcome": outcome,
            "run_number": len(history) + 1,
            "infra_runs": (previous or {}).get("infra_runs", 0)
            + (outcome == INFRASTRUCTURE_FAILURE),
            "started": started,
            "finished": datetime.now(UTC).isoformat(timespec="seconds"),
            **metadata,
            "result": result,
            "history": [*history, {"started": started, "outcome": outcome, "error_code": code}],
        }
        _write_json(path, record)
        echo(f"{pdf.stem}: {outcome}" + (f" ({code})" if code else ""))

        if outcome == CONFIGURATION_ERROR:
            echo(f"Stopping: configuration error {code}. Fix it, then rerun to resume.")
            return EXIT_CONFIG, run_dir
        if code == LLMErrorCode.RATE_LIMITED:
            echo("Stopping: rate limit or quota reached (429). Rerun later to resume.")
            return EXIT_STOPPED_QUOTA, run_dir
    return EXIT_OK, run_dir


# --- report ------------------------------------------------------------------


def _cell(value: Any) -> str:
    text = "null" if value is None else str(value)
    return "`" + text.replace("|", "\\|").replace("`", "'") + "`"


def compare_record(record: dict[str, Any]) -> DocComparison:
    doc_id = record["doc_id"]
    truth = json.loads((DEV_DIR / "truth" / f"{doc_id}.json").read_text(encoding="utf-8"))
    result = record.get("result") or {}
    text = extract_text(DEV_DIR / "pdf" / f"{doc_id}.pdf", max_pages=100).text
    return compare_document(
        truth,
        result.get("raw"),
        result.get("normalized"),
        result.get("flags") or [],
        error_code=(result.get("error") or {}).get("code"),
        document_text=text,
    )


def build_report(run_dir: Path) -> str:
    records = [r for r in (_load(p) for p in sorted(run_dir.glob("dev-*.json"))) if r]
    lines = [
        f"# Dev check: {run_dir.name}",
        "",
        "Development aid on the dev set only. These counts are not reported metrics.",
        "",
        "| Doc | Outcome | Status | Layer 1 | Layer 2 | Ambiguous | Lines matched / truth"
        " (extra) | Flags | Arithmetic |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    diffs: list[str] = []
    for record in records:
        result = record.get("result") or {}
        if record["outcome"] == INFRASTRUCTURE_FAILURE:
            code = (result.get("error") or {}).get("code")
            lines.append(
                f"| {record['doc_id']} | not scored: infrastructure ({code}), "
                f"{record['infra_runs']} run(s) | | | | | | | |"
            )
            continue
        c = compare_record(record)
        n = len(c.fields)
        if not c.arithmetic_consistent:
            fired = c.expected_arithmetic_flag in c.flag_codes
            arithmetic = f"expected {c.expected_arithmetic_flag}: {'yes' if fired else 'NO'}"
        else:
            arithmetic = "unexpected flag" if c.arithmetic_flag_fired else "valid"
        lines.append(
            f"| {c.doc_id} | {record['outcome']} | {result.get('status', '')} "
            f"| {c.count('layer1')}/{n} | {c.count('layer2')}/{n} | {c.ambiguous} "
            f"| {len(c.matched_lines)}/{c.truth_lines} ({len(c.extra_lines)}) "
            f"| {', '.join(c.flag_codes) or 'none'} | {arithmetic} |"
        )
        for f in c.fields:
            if f.differs:
                diffs.append(
                    f"| {c.doc_id} | {f.path} | {'yes' if f.layer1 else 'no'} | {f.outcome} "
                    f"| {_cell(f.raw)} | {_cell(f.printed)} | {_cell(f.normalized)} "
                    f"| {_cell(f.value)} | {f.note} |"
                )
        truth_lines = json.loads(
            (DEV_DIR / "truth" / f"{c.doc_id}.json").read_text(encoding="utf-8")
        )["line_items"]
        for t in c.missing_lines if c.failure is None else []:
            description = truth_lines[t]["description"]["printed"]
            diffs.append(
                f"| {c.doc_id} | line_items[{t}] | | line missing | | {_cell(description)} | | | |"
            )
        predicted = (result.get("normalized") or {}).get("line_items") or []
        for p in c.extra_lines:
            description = predicted[p].get("description")
            diffs.append(
                f"| {c.doc_id} | predicted line {p} | | extra line | {_cell(description)} | | | | |"
            )

    lines += ["", "## Fields that differ", ""]
    if diffs:
        lines += [
            "| Doc | Field | Layer 1 | Layer 2 | Raw | Printed (truth) | Normalized"
            " | Value (truth) | Note |",
            "|---|---|---|---|---|---|---|---|---|",
            *diffs,
        ]
    else:
        lines.append("None.")
    done = {r["doc_id"] for r in records}
    not_run = sorted(p.stem for p in (DEV_DIR / "pdf").glob("dev-*.pdf") if p.stem not in done)
    if not_run:
        lines += ["", f"Not run yet: {', '.join(not_run)}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.dev_check", description=__doc__)
    parser.add_argument("--only", action="append", metavar="DEV_ID", help="e.g. dev-09")
    parser.add_argument("--provider", choices=["fake", "gemini"], help="override LLM_PROVIDER")
    parser.add_argument(
        "--retry-infra",
        action="store_true",
        help=f"retry documents that failed for infrastructure reasons {MAX_INFRA_RUNS} times",
    )
    parser.add_argument("--report-only", action="store_true", help="rebuild report.md only")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = Settings(**({"llm_provider": args.provider} if args.provider else {}))
    try:
        provider = get_provider(settings)
        if args.report_only:
            code, run_dir = EXIT_OK, run_dir_for(RESULTS_ROOT, provider)
        else:
            code, run_dir = run_documents(
                settings, provider, only=args.only, retry_infra=args.retry_infra
            )
    except LLMError as error:
        print(f"{error.code}: {error.message}")
        return EXIT_CONFIG
    except DevCheckError as error:
        print(f"Error: {error}")
        return EXIT_CONFIG

    report = build_report(run_dir)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print()
    print(report)
    print(f"Results: {run_dir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
