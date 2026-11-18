"""Compute the reported metrics for one evaluation run (docs/METRICS.md v1.1).

    backend\\.venv\\Scripts\\python.exe -m eval.metrics eval/results/test/<run folder>

Reads run.json, predictions.jsonl, the set's truth files and PDF text (local
only; no API calls). Writes, next to them:
- results.json: run metadata and every metric, with counts. The report
  generator (python -m eval.report) reads only this file.
- error_analysis.json: one entry per error, with an automatic cause.
- error_notes.md: the same errors as a table to confirm causes by hand.
  Created once and never overwritten (your edits are kept).

Scoring per document uses app.eval_compare (layers 1 and 2, ambiguous
outcome, line matching), the same code the dev checks used.
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.eval_compare import (
    ARITHMETIC_CODES,
    HEADER_FIELDS,
    INFRASTRUCTURE_FAILURE,
    LINE_FIELDS,
    METRICS_VERSION,
    MODEL_FAILURE,
    DocComparison,
    FieldResult,
    compare_document,
)
from app.pdf_text import extract_text
from app.schemas.invoice import RawExtraction
from app.validation.checks import check_invoice
from app.validation.grounding import DocumentText, is_grounded
from eval.run_test import (
    CONFIGURATION_ERROR,
    MAX_RUNS,
    SUCCESS,
    infra_runs,
    latest_by_document,
    read_predictions,
)
from eval.sets import REPO_ROOT, EvalSet, document_ids, get_set, load_truth, pdf_path

ERROR_OUTCOMES = ("wrong", "missing", "hallucinated")
CASE_STUDY_BELOW = 5  # METRICS section 8: groups under 5 documents are case studies
GROUNDING = "VALUE_NOT_IN_DOCUMENT"


class MetricsError(Exception):
    pass


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    """A count pair; the percentage is derived, never stored alone."""
    return {
        "n": numerator,
        "d": denominator,
        "pct": round(100 * numerator / denominator, 1) if denominator else None,
    }


def spread(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "median": None, "n_documents": 0}
    return {
        "mean": round(statistics.fmean(values), 2),
        "median": statistics.median(values),
        "n_documents": len(values),
    }


# --- oracle run (METRICS section 4) ---------------------------------------------


def oracle_ambiguous_paths(truth: dict[str, Any]) -> set[str]:
    """Field paths the normalizer calls ambiguous on the truth printed strings
    (a perfect extractor). Line paths use truth line indices."""
    raw = {name: truth["fields"][name]["printed"] for name in HEADER_FIELDS}
    raw["line_items"] = [
        {name: line[name]["printed"] for name in LINE_FIELDS} for line in truth["line_items"]
    ]
    flags = check_invoice(RawExtraction.model_validate(raw)).flags
    return {flag.field_path for flag in flags if flag.code.endswith("_AMBIGUOUS")}


# --- per document ---------------------------------------------------------------


@dataclass
class ScoredDocument:
    doc_id: str
    truth: dict[str, Any]
    record: dict[str, Any]
    comparison: DocComparison
    oracle_ambiguous: set[str]
    text: str
    flags: list[dict[str, Any]] = field(default_factory=list)
    field_flags: dict[str, list[str]] = field(default_factory=dict)  # truth path -> codes
    flags_on_unmatched_lines: int = 0

    @property
    def features(self) -> list[str]:
        return self.truth.get("features", [])


def _map_flags(doc: ScoredDocument) -> None:
    """Attach each flag to the field instances it names (truth paths)."""
    c = doc.comparison
    to_truth = {p: t for t, p in c.matched_lines}
    paths = {f.path for f in c.fields}
    for flag in doc.flags:
        path, code = flag["field_path"], flag["code"]
        if path in HEADER_FIELDS:
            targets = [path]
        elif path == "line_items":  # the table: every line-item field instance
            targets = [p for p in paths if p.startswith("line_items[")]
        elif path.startswith("line_items["):
            index = int(path[len("line_items[") : path.index("]")])
            name = path.split(".", 1)[1]
            if index not in to_truth:
                doc.flags_on_unmatched_lines += 1
                continue
            targets = [f"line_items[{to_truth[index]}].{name}"]
        else:
            targets = []
        for target in targets:
            doc.field_flags.setdefault(target, []).append(code)


def score_document(eval_set: EvalSet, doc_id: str, record: dict[str, Any] | None) -> ScoredDocument:
    truth = load_truth(eval_set, doc_id)
    text = extract_text(pdf_path(eval_set, doc_id), max_pages=100).text
    result = (record or {}).get("result") or {}
    flags = result.get("flags") or []
    model_failed = (record or {}).get("outcome") == MODEL_FAILURE
    comparison = compare_document(
        truth,
        None if model_failed else result.get("raw"),
        None if model_failed else result.get("normalized"),
        flags,
        error_code=(record or {}).get("error_code") if model_failed else None,
        document_text=text,
    )
    if model_failed:
        comparison.failure = MODEL_FAILURE
    doc = ScoredDocument(
        doc_id, truth, record or {}, comparison, oracle_ambiguous_paths(truth), text, flags
    )
    _map_flags(doc)
    return doc


# --- aggregation ------------------------------------------------------------------


def field_counts(docs: list[ScoredDocument]) -> dict[str, Any]:
    fields = [f for d in docs for f in d.comparison.fields]
    outcomes = Counter(f.outcome for f in fields)
    ambiguous = [(d, f) for d in docs for f in d.comparison.fields if f.outcome == "ambiguous"]
    document_ambiguity = sum(1 for d, f in ambiguous if f.path in d.oracle_ambiguous)
    accurate = sum(1 for f in fields if f.layer2)
    total = len(fields)
    return {
        "field_instances": total,
        "layer1": ratio(sum(1 for f in fields if f.layer1), total),
        "layer2_strict": ratio(accurate, total),
        "layer2_decided": ratio(accurate, total - outcomes["ambiguous"]),
        "outcomes": {
            k: outcomes.get(k, 0)
            for k in ("correct", "correct_absent", *ERROR_OUTCOMES, "ambiguous")
        },
        "errors": sum(outcomes.get(k, 0) for k in ERROR_OUTCOMES),
        "ambiguous": {
            "total": outcomes["ambiguous"],
            "document_ambiguity": document_ambiguity,
            "induced_ambiguity": outcomes["ambiguous"] - document_ambiguity,
        },
        "currency_layer1_exceptions": sum(d.comparison.currency_exceptions for d in docs),
    }


def _field_type(path: str) -> str:
    return path.split(".", 1)[1] if path.startswith("line_items[") else path


def per_field(docs: list[ScoredDocument]) -> dict[str, Any]:
    table = {}
    for name in (*HEADER_FIELDS, *LINE_FIELDS):
        fields = [f for d in docs for f in d.comparison.fields if _field_type(f.path) == name]
        ambiguous = sum(1 for f in fields if f.outcome == "ambiguous")
        accurate = sum(1 for f in fields if f.layer2)
        table[name] = {
            "layer1": ratio(sum(1 for f in fields if f.layer1), len(fields)),
            "layer2_strict": ratio(accurate, len(fields)),
            "layer2_decided": ratio(accurate, len(fields) - ambiguous),
            "ambiguous": ambiguous,
            "errors": sum(1 for f in fields if f.outcome in ERROR_OUTCOMES),
        }
    return table


def _header_ok(doc: ScoredDocument) -> bool:
    return all(f.layer2 for f in doc.comparison.fields if "[" not in f.path)


def _lines_ok(doc: ScoredDocument) -> bool:
    c = doc.comparison
    line_fields = [f for f in c.fields if f.path.startswith("line_items[")]
    return not c.missing_lines and not c.extra_lines and all(f.layer2 for f in line_fields)


def document_accuracy(docs: list[ScoredDocument]) -> dict[str, Any]:
    only_ambiguous = 0
    for d in docs:
        problems = [f for f in d.comparison.fields if not f.layer2]
        if (
            problems
            and all(f.outcome == "ambiguous" for f in problems)
            and not (d.comparison.missing_lines or d.comparison.extra_lines)
        ):
            only_ambiguous += 1
    return {
        "header_only": ratio(sum(_header_ok(d) for d in docs), len(docs)),
        "full": ratio(sum(_header_ok(d) and _lines_ok(d) for d in docs), len(docs)),
        "only_ambiguous_problems": only_ambiguous,
    }


def line_metrics(docs: list[ScoredDocument]) -> dict[str, Any]:
    truth = sum(d.comparison.truth_lines for d in docs)
    predicted = sum(d.comparison.predicted_lines for d in docs)
    matched = sum(len(d.comparison.matched_lines) for d in docs)
    tp = 0
    for d in docs:
        for t, _ in d.comparison.matched_lines:
            fields = [f for f in d.comparison.fields if f.path.startswith(f"line_items[{t}].")]
            tp += all(f.layer2 for f in fields)
    precision, recall = ratio(tp, predicted), ratio(tp, truth)
    p, r = (tp / predicted if predicted else 0.0), (tp / truth if truth else 0.0)
    f1 = round(100 * 2 * p * r / (p + r), 1) if p + r else None
    matched_fields = {}
    for name in LINE_FIELDS:
        fields = [
            f for d in docs for f in d.comparison.fields
            if f.path.startswith("line_items[") and _field_type(f.path) == name
        ]  # fmt: skip
        matched_fields[name] = ratio(sum(f.layer2 for f in fields), len(fields))
    return {
        "truth_lines": truth,
        "predicted_lines": predicted,
        "matched_lines": matched,
        "true_positive_lines": tp,
        "precision": precision,
        "recall": recall,
        "f1_pct": f1,
        "match_rate": ratio(matched, truth),
        "field_accuracy_over_matched": matched_fields,
    }


def _arith_fields(doc: ScoredDocument) -> dict[str, list[str]]:
    by_code: dict[str, list[str]] = {}
    for flag in doc.flags:
        if flag["code"] in ARITHMETIC_CODES:
            by_code.setdefault(flag["code"], []).append(flag["field_path"])
    return by_code


def arithmetic(docs: list[ScoredDocument]) -> dict[str, Any]:
    scored = [d for d in docs if d.comparison.failure is None]
    consistent = [d for d in scored if d.comparison.arithmetic_consistent]
    cases = []
    for d in docs:
        c = d.comparison
        if c.arithmetic_consistent:
            continue
        flagged = _arith_fields(d)
        cases.append(
            {
                "doc_id": d.doc_id,
                "expected_code": c.expected_arithmetic_flag,
                "expected_fired": c.expected_arithmetic_flag in flagged,
                "arithmetic_flags": flagged,
                "extraction_failed": c.failure is not None,
            }
        )
    return {
        "consistent_valid": ratio(
            sum(not d.comparison.arithmetic_flag_fired for d in consistent), len(consistent)
        ),
        "consistent_with_flags": [
            d.doc_id for d in consistent if d.comparison.arithmetic_flag_fired
        ],
        "deliberate_cases": cases,
    }


def _explained(doc: ScoredDocument, f: FieldResult, code: str) -> bool:
    if code in ARITHMETIC_CODES and not doc.comparison.arithmetic_consistent:
        return True
    return code.endswith("_AMBIGUOUS") and f.path in doc.oracle_ambiguous


def flag_metrics(docs: list[ScoredDocument]) -> dict[str, Any]:
    errors = flagged_errors = false_alarms = explained = failed_document_errors = 0
    items, instances, all_fields = [], [], []
    for d in docs:
        for f in d.comparison.fields:
            if f.outcome == "ambiguous":
                continue  # flagged by construction; reported in section 4
            codes = d.field_flags.get(f.path, [])
            if f.outcome in ERROR_OUTCOMES:
                errors += 1
                flagged_errors += bool(codes)
                failed_document_errors += d.comparison.failure is not None
            elif codes:
                if all(_explained(d, f, code) for code in codes):
                    explained += 1
                else:
                    false_alarms += 1
        paths = {flag["field_path"] for flag in d.flags}
        items.append(len(paths))
        instances.append(len(d.field_flags))
        all_fields.append(len(d.comparison.fields))
    unflagged = errors - flagged_errors
    return {
        "error_fields": errors,
        "flagged_error_fields": flagged_errors,
        "false_alarms": false_alarms,
        "explained_flags_on_accurate_fields": explained,
        "recall": ratio(flagged_errors, errors),
        "precision": ratio(flagged_errors, flagged_errors + false_alarms),
        # Fields of model-failed documents: no field flags, but the whole
        # document shows as failed to the reviewer. Included in the misses above.
        "errors_in_failed_documents": failed_document_errors,
        "missed_errors_per_document": {
            "unflagged_errors": unflagged,
            "documents": len(docs),
            "value": round(unflagged / len(docs), 2) if docs else None,
        },
        "review_items_per_document": spread(items),
        "flagged_instances_per_document": spread(instances),
        "flags_on_unmatched_predicted_lines": sum(d.flags_on_unmatched_lines for d in docs),
        "reference": {
            "no_review": {"load": 0, "recall": ratio(0, errors)},
            "review_every_field": {
                "load_per_document": spread(all_fields),
                "recall": ratio(errors, errors),
            },
        },
    }


# --- groups (METRICS section 8) ---------------------------------------------------


def _group_definitions(docs: list[ScoredDocument]) -> list[tuple[str, str, list[str]]]:
    """(key, label, document ids) for every requested breakdown."""

    def having(feature: str) -> list[str]:
        return [d.doc_id for d in docs if feature in d.features]

    def prefixed(prefix: str) -> list[str]:
        return [d.doc_id for d in docs if any(f.startswith(prefix) for f in d.features)]

    layouts = sorted({d.truth.get("layout") for d in docs if d.truth.get("layout")})
    groups = [(f"layout:{name}", f"Layout: {name}", having(f"layout:{name}")) for name in layouts]
    jpy, cad = having("currency:JPY"), having("currency:CAD")
    others = [d.doc_id for d in docs if d.doc_id not in jpy + cad]
    groups += [
        ("currency:JPY", "Currency JPY", jpy),
        ("currency:CAD", "Currency CAD", cad),
        ("currency:other", "Other currencies", others),
        ("numbers:plain", "Plain numbers (no separators)", having("numbers:plain")),
        ("amount_before_qty", "Amount column before quantity", having("amount_before_qty")),
        ("sku_column", "SKU / item-code column", having("sku_column")),
        ("wrapped_descriptions", "Wrapped descriptions", having("wrapped_descriptions")),
        ("injection", "Prompt-injection line", having("injection")),
        ("arith_error", "Deliberate arithmetic error", prefixed("arith_error:")),
        (
            "ambiguity",
            "Document ambiguity (oracle)",
            [d.doc_id for d in docs if d.oracle_ambiguous],
        ),
    ]
    return [g for g in groups if g[2]]


def case_summary(doc: ScoredDocument) -> dict[str, Any]:
    c = doc.comparison
    n = len(c.fields)
    return {
        "doc_id": doc.doc_id,
        "outcome": doc.record.get("outcome"),
        "layer1": f"{c.count('layer1')} of {n} fields",
        "layer2": f"{c.count('layer2')} of {n} fields",
        "ambiguous": c.ambiguous,
        "errors": [
            {"path": f.path, "outcome": f.outcome, "raw": f.raw, "printed": f.printed}
            for f in c.fields
            if f.outcome in ERROR_OUTCOMES
        ],
        "lines": f"{len(c.matched_lines)} of {c.truth_lines} matched, {len(c.extra_lines)} extra",
        "flags": sorted({flag["code"] for flag in doc.flags}),
        "expected_arithmetic_flag": c.expected_arithmetic_flag,
    }


def _slice(docs: list[ScoredDocument]) -> dict[str, Any]:
    counts = field_counts(docs)
    lines = line_metrics(docs)
    return {
        "documents": len(docs),
        "field_instances": counts["field_instances"],
        "layer1": counts["layer1"],
        "layer2_strict": counts["layer2_strict"],
        "layer2_decided": counts["layer2_decided"],
        "ambiguous": counts["ambiguous"]["total"],
        "errors": counts["errors"],
        "line_recall": lines["recall"],
        "flag_recall": flag_metrics(docs)["recall"],
    }


@dataclass
class Member:
    """Group membership facts for any document, scored or not."""

    doc_id: str
    truth: dict[str, Any]
    oracle_ambiguous: set[str]

    @property
    def features(self) -> list[str]:
        return self.truth.get("features", [])


def groups(docs: list[ScoredDocument], everyone: list[Member]) -> list[dict[str, Any]]:
    """Membership comes from every document of the set, so a document that was
    never scored still shows in its group (as not scored); counts come from the
    scored documents. The case-study rule uses the group's full size."""
    by_id = {d.doc_id: d for d in docs}
    out = []
    for key, label, ids in _group_definitions(everyone):
        members = [by_id[i] for i in ids if i in by_id]
        rest = [d for d in docs if d.doc_id not in ids]
        case_study = len(ids) < CASE_STUDY_BELOW
        entry = {
            "key": key,
            "label": label,
            "doc_ids": ids,
            "not_scored": [i for i in ids if i not in by_id],
            "case_study": case_study,
            "counts": _slice(members),
            "rest": _slice(rest),
        }
        if case_study:
            entry["cases"] = [case_summary(d) for d in members]
        out.append(entry)
    return out


# --- error analysis (METRICS section 9) -------------------------------------------


def _auto_cause(doc: ScoredDocument, f: FieldResult, document: DocumentText) -> tuple[str, str]:
    error_code = doc.record.get("error_code")
    if doc.comparison.failure == MODEL_FAILURE:
        if error_code == "SCHEMA_VALIDATION_FAILED":
            return "schema_failure", "document failed schema validation"
        return "unassigned", f"model failure {error_code}; assign by hand"
    if f.layer1:
        return "normalization", "layer 1 correct, layer 2 wrong"
    if f.printed is None:
        return "extraction", "value not printed on the document (hallucinated)"
    if document.contains(str(f.printed)):
        return "extraction", "truth string is contiguous in the text; check for a nearby distractor"
    if document.contains_wrapped(str(f.printed)):
        return "layout", "truth string is split across lines in the text layer"
    return "layout", "truth string is not contiguous in the text layer"


def error_analysis(docs: list[ScoredDocument]) -> dict[str, Any]:
    errors, lines, grounding_false_alarms, grounding_misses, inconsistencies = [], [], [], [], []
    for d in docs:
        document = DocumentText(d.text)
        c = d.comparison
        for f in c.fields:
            codes = d.field_flags.get(f.path, [])
            if f.outcome in ERROR_OUTCOMES:
                cause, note = _auto_cause(d, f, document)
                errors.append(
                    {
                        "doc_id": d.doc_id,
                        "path": f.path,
                        "outcome": f.outcome,
                        "layer1": f.layer1,
                        "raw": f.raw,
                        "printed": f.printed,
                        "normalized": f.normalized,
                        "value": f.value,
                        "flags": codes,
                        "auto_cause": cause,
                        "auto_note": note,
                    }
                )
                if (
                    f.raw is not None
                    and GROUNDING not in codes
                    and not is_grounded(str(f.raw), document, _field_type(f.path))
                ):
                    grounding_misses.append({"doc_id": d.doc_id, "path": f.path, "raw": f.raw})
            elif f.layer2 and GROUNDING in codes:
                grounding_false_alarms.append({"doc_id": d.doc_id, "path": f.path, "raw": f.raw})
        truth_lines = d.truth["line_items"]
        if c.failure is None:
            for t in c.missing_lines:
                lines.append(
                    {"doc_id": d.doc_id, "kind": "truth line not matched", "line": t,
                     "description": truth_lines[t]["description"]["printed"]}
                )  # fmt: skip
            predicted = ((d.record.get("result") or {}).get("normalized") or {}).get(
                "line_items"
            ) or []
            for p in c.extra_lines:
                lines.append(
                    {"doc_id": d.doc_id, "kind": "extra predicted line", "line": p,
                     "description": predicted[p].get("description")}
                )  # fmt: skip
        if not c.arithmetic_consistent:
            inconsistencies.append(
                {
                    "doc_id": d.doc_id,
                    "expected": c.expected_arithmetic_flag,
                    "flags": _arith_fields(d),
                }
            )
    return {
        "field_errors": errors,
        "by_cause": dict(Counter(e["auto_cause"] for e in errors)),
        "line_errors": lines,
        "grounding": {
            "false_alarms": grounding_false_alarms,
            "should_have_caught": grounding_misses,
        },
        "document_inconsistency": inconsistencies,
    }


def error_notes(analysis: dict[str, Any], run_name: str) -> str:
    def cell(value: Any) -> str:
        text = "null" if value is None else str(value)
        return "`" + text.replace("|", "\\|").replace("`", "'") + "`"

    rows = [
        f"# Error notes: {run_name}",
        "",
        "Automatic causes follow docs/METRICS.md section 9. Confirm each one by hand:",
        "write the confirmed cause (extraction, layout, normalization, schema_failure)",
        "and a short reason in the last two columns. This file is never overwritten.",
        "",
        "| # | Doc | Field | Outcome | Raw | Printed (truth) | Auto cause | Auto note"
        " | Confirmed cause | Reason |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(analysis["field_errors"], 1):
        rows.append(
            f"| {i} | {e['doc_id']} | {e['path']} | {e['outcome']} | {cell(e['raw'])} "
            f"| {cell(e['printed'])} | {e['auto_cause']} | {e['auto_note']} |  |  |"
        )
    rows += [
        "",
        "## Line-level errors",
        "",
        "| Doc | Kind | Line | Description | Cause | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for e in analysis["line_errors"]:
        rows.append(
            f"| {e['doc_id']} | {e['kind']} | {e['line']} | {cell(e['description'])} |  |  |"
        )
    return "\n".join(rows) + "\n"


# --- driver -------------------------------------------------------------------------


def compute(run_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    eval_set = get_set(meta["set"])
    records = read_predictions(run_dir / "predictions.jsonl")
    latest = latest_by_document(records)
    ids = document_ids(eval_set)

    if any(r["outcome"] == CONFIGURATION_ERROR for r in latest.values()):
        bad = sorted(d for d, r in latest.items() if r["outcome"] == CONFIGURATION_ERROR)
        raise MetricsError(f"Configuration errors on {bad}: the run is not valid (METRICS 2a).")

    not_attempted = [d for d in ids if d not in latest]
    never_succeeded, pending = [], []
    for d in ids:
        if d in latest and latest[d]["outcome"] == INFRASTRUCTURE_FAILURE:
            (never_succeeded if infra_runs(records, d) >= MAX_RUNS else pending).append(d)
    model_failures = sorted(d for d, r in latest.items() if r["outcome"] == MODEL_FAILURE)
    scored_ids = [
        d for d in ids if d in latest and latest[d]["outcome"] in (SUCCESS, MODEL_FAILURE)
    ]
    docs = [score_document(eval_set, d, latest[d]) for d in scored_ids]
    everyone = [
        Member(d, truth, oracle_ambiguous_paths(truth))
        for d, truth in ((d, load_truth(eval_set, d)) for d in ids)
    ]

    counts = field_counts(docs)
    unscored = never_succeeded + pending + not_attempted
    worst = None
    if unscored:
        extra = len(HEADER_FIELDS) * len(unscored)  # counted as missing (worst case)
        worst = ratio(counts["layer2_strict"]["n"], counts["field_instances"] + extra)

    documents = {}
    for d in ids:
        history = [
            {"run": r["run_number"], "outcome": r["outcome"], "error_code": r["error_code"]}
            for r in records
            if r["doc_id"] == d
        ]
        documents[d] = {
            "outcome": latest[d]["outcome"] if d in latest else "not_attempted",
            "run_number": latest[d]["run_number"] if d in latest else None,
            "history": history,
            "features": load_truth(eval_set, d).get("features", []),
        }

    analysis = error_analysis(docs)
    results = {
        "metadata": {k: v for k, v in meta.items() if k != "runs"},
        "runs": meta["runs"],
        "computed": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "metrics_version": METRICS_VERSION,
        "status": {
            "complete": not (pending or not_attempted),
            "documents": len(ids),
            "scored": len(docs),
            "successes": len(docs) - len(model_failures),
            "model_failures": model_failures,
            "never_succeeded_infrastructure": never_succeeded,
            "pending_infrastructure_retry": pending,
            "not_attempted": not_attempted,
        },
        "fields": counts,
        "layer2_strict_worst_case": worst,
        "per_field": per_field(docs),
        "document_accuracy": document_accuracy(docs),
        "lines": line_metrics(docs),
        "arithmetic": arithmetic(docs),
        "flags": flag_metrics(docs),
        "groups": groups(docs, everyone),
        "error_causes": analysis["by_cause"],
        "documents": documents,
    }
    if meta["metrics_version"] != METRICS_VERSION:
        results["metadata"]["note"] = (
            f"run recorded metrics version {meta['metrics_version']}, scored with {METRICS_VERSION}"
        )
    return {"results": results, "analysis": analysis}


def write_outputs(run_dir: Path, computed: dict[str, Any]) -> list[Path]:
    written = []
    for name, key in (("results.json", "results"), ("error_analysis.json", "analysis")):
        path = run_dir / name
        path.write_text(
            json.dumps(computed[key], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written.append(path)
    notes = run_dir / "error_notes.md"
    if not notes.exists():
        notes.write_text(error_notes(computed["analysis"], run_dir.name), encoding="utf-8")
        written.append(notes)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.metrics", description=__doc__)
    parser.add_argument("run_dir", type=Path, help="e.g. eval/results/test/<run folder>")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_dir = args.run_dir if args.run_dir.is_absolute() else REPO_ROOT / args.run_dir
    try:
        computed = compute(run_dir)
    except (MetricsError, FileNotFoundError) as error:
        print(f"Error: {error}")
        return 2
    for path in write_outputs(run_dir, computed):
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    status = computed["results"]["status"]
    if not status["complete"]:
        print("Note: the run is not complete; results are marked incomplete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
