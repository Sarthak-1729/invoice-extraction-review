# ruff: noqa: E501  (Markdown table rows read best on one line each)
"""Write README-ready Markdown tables from one results.json (and nothing else).

    backend\\.venv\\Scripts\\python.exe -m eval.report eval/results/test/<run folder>

Writes report.md next to results.json. Rules from docs/METRICS.md section 8:
every percentage has its counts next to it, and groups under 5 documents are
case studies (counts per document, no percentages).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def pct(r: dict[str, Any] | None) -> str:
    if not r:
        return "n/a"
    if not r["d"]:
        return f"n/a ({r['n']}/{r['d']})"
    return f"{r['pct']:.1f}% ({r['n']}/{r['d']})"


def counts_only(r: dict[str, Any]) -> str:
    return f"{r['n']} of {r['d']}"


def code(value: Any) -> str:
    text = "null" if value is None else str(value)
    return "`" + text.replace("|", "\\|").replace("`", "'") + "`"


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
        *("| " + " | ".join(str(c) for c in row) + " |" for row in rows),
    ]


def coverage_sentence(res: dict[str, Any]) -> str:
    s = res["status"]
    parts = [f"{s['scored']} of {s['documents']} documents scored"]
    if s["never_succeeded_infrastructure"]:
        parts.append(f"{len(s['never_succeeded_infrastructure'])} never succeeded (infrastructure)")
    if s["model_failures"]:
        n = len(s["model_failures"])
        parts.append(f"{n} extraction failure{'s' if n != 1 else ''} counted as missing")
    return "; ".join(parts)


def build_report(res: dict[str, Any]) -> str:
    meta, status, fields = res["metadata"], res["status"], res["fields"]
    out = [f"# Evaluation: {meta['set']} set", ""]
    if not status["complete"]:
        out += [
            "> **Incomplete run.** "
            + ", ".join(
                f"{label}: {', '.join(ids)}"
                for label, ids in (
                    ("pending infrastructure retry", status["pending_infrastructure_retry"]),
                    ("not attempted", status["not_attempted"]),
                )
                if ids
            )
            + ". These numbers are not final.",
            "",
        ]
    settings = ", ".join(f"{k}={v}" for k, v in meta["settings"].items())
    out += _table(
        ["Run", "Value"],
        [
            ["Model", f"{meta['provider']} / {meta['model']}"],
            ["Prompt", f"{meta['prompt_version']} (`{meta['prompt_hash'][:12]}`)"],
            [
                "Git commit",
                f"`{meta['git_commit'][:12]}`" + (" (dirty tree)" if meta["git_dirty"] else ""),
            ],
            ["Set hash", f"`{meta['set_sha256']}`"],
            ["Metric definitions", f"v{res['metrics_version']}"],
            ["Runs", f"{len(res['runs'])} (started {meta['created']})"],
            ["Computed", res["computed"]],
            ["Settings", settings],
        ],
    )
    covered = coverage_sentence(res)
    out += ["", "## Headline", ""]
    out += _table(
        ["Metric", "Result"],
        [
            [
                "Layer 2 decided accuracy",
                f"{pct(fields['layer2_decided'])}, {fields['ambiguous']['total']} ambiguous excluded",
            ],
            ["Layer 2 strict accuracy", pct(fields["layer2_strict"])],
            *(
                [
                    [
                        "Layer 2 strict, unscored documents as missing",
                        pct(res["layer2_strict_worst_case"]),
                    ]
                ]
                if res.get("layer2_strict_worst_case")
                else []
            ),
            ["Layer 1 (printed string copied exactly)", pct(fields["layer1"])],
            [
                "Line items F1",
                f"{res['lines']['f1_pct']}% (precision {pct(res['lines']['precision'])}, recall {pct(res['lines']['recall'])})",
            ],
            ["Flag recall (errors flagged)", pct(res["flags"]["recall"])],
            ["Flag precision", pct(res["flags"]["precision"])],
        ],
    )
    out += ["", f"Coverage: {covered}.", ""]
    if status["model_failures"]:
        out.append(
            f"Extraction failures (counted as missing): {', '.join(status['model_failures'])}."
        )
    if status["never_succeeded_infrastructure"]:
        out.append(
            "Never succeeded (infrastructure, left out of accuracy denominators): "
            + ", ".join(status["never_succeeded_infrastructure"])
            + "."
        )
    if fields["currency_layer1_exceptions"]:
        out.append(
            f"Layer 1 currency exception applied to {fields['currency_layer1_exceptions']} field(s)."
        )

    out += ["", "## Per field (layer 1 and layer 2 side by side)", ""]
    out += _table(
        ["Field", "Layer 1", "Layer 2 strict", "Layer 2 decided", "Ambiguous", "Errors"],
        [
            [
                name,
                pct(r["layer1"]),
                pct(r["layer2_strict"]),
                pct(r["layer2_decided"]),
                r["ambiguous"],
                r["errors"],
            ]
            for name, r in res["per_field"].items()
        ],
    )
    o, a = fields["outcomes"], fields["ambiguous"]
    out += ["", "## Outcomes and ambiguity", ""]
    out += _table(
        ["Outcome", "Fields"],
        [[k, v] for k, v in o.items()]
        + [
            [
                "ambiguous: document ambiguity (oracle also ambiguous; handled)",
                a["document_ambiguity"],
            ],
            ["ambiguous: induced by the extraction", a["induced_ambiguity"]],
        ],
    )

    d = res["document_accuracy"]
    out += ["", "## Documents", ""]
    out += _table(
        ["Measure", "Result"],
        [
            ["Header correct (all 9 fields, strict)", pct(d["header_only"])],
            ["Fully correct (header and every line)", pct(d["full"])],
            ["Documents whose only problems are ambiguous fields", d["only_ambiguous_problems"]],
        ],
    )

    lines = res["lines"]
    out += ["", "## Line items", ""]
    out += _table(
        ["Measure", "Result"],
        [
            [
                "Truth lines / predicted lines",
                f"{lines['truth_lines']} / {lines['predicted_lines']}",
            ],
            ["Precision (all 4 fields right)", pct(lines["precision"])],
            ["Recall (all 4 fields right)", pct(lines["recall"])],
            ["F1", f"{lines['f1_pct']}%"],
            ["Match rate (description matched)", pct(lines["match_rate"])],
            *(
                [f"{name} accuracy over matched lines", pct(r)]
                for name, r in lines["field_accuracy_over_matched"].items()
            ),
        ],
    )

    ar = res["arithmetic"]
    out += [
        "",
        "## Arithmetic",
        "",
        f"Consistent documents with no arithmetic flag: {pct(ar['consistent_valid'])}.",
    ]
    if ar["consistent_with_flags"]:
        out.append(
            f"Consistent documents that were flagged anyway: {', '.join(ar['consistent_with_flags'])}."
        )
    out += ["", "Deliberate arithmetic errors (case studies):", ""]
    out += _table(
        ["Document", "Expected flag", "Fired", "Arithmetic flags (fields)"],
        [
            [
                c["doc_id"],
                c["expected_code"],
                "extraction failed"
                if c["extraction_failed"]
                else ("yes" if c["expected_fired"] else "**no**"),
                "; ".join(f"{k}: {', '.join(v)}" for k, v in c["arithmetic_flags"].items())
                or "none",
            ]
            for c in ar["deliberate_cases"]
        ],
    )

    fl = res["flags"]
    missed = fl["missed_errors_per_document"]
    out += ["", "## Flagging and review load", ""]
    out += _table(
        [
            "",
            "Recall",
            "Review items per document (mean / median)",
            "Flagged fields per document (mean / median)",
        ],
        [
            ["No review", pct(fl["reference"]["no_review"]["recall"]), "0", "0"],
            [
                "This system",
                pct(fl["recall"]),
                f"{fl['review_items_per_document']['mean']} / {fl['review_items_per_document']['median']}",
                f"{fl['flagged_instances_per_document']['mean']} / {fl['flagged_instances_per_document']['median']}",
            ],
            [
                "Review every field",
                pct(fl["reference"]["review_every_field"]["recall"]),
                "n/a",
                f"{fl['reference']['review_every_field']['load_per_document']['mean']} / "
                f"{fl['reference']['review_every_field']['load_per_document']['median']}",
            ],
        ],
    )
    out += [
        "",
        f"- Flag precision: {pct(fl['precision'])} (false alarms: {fl['false_alarms']}).",
        f"- Explained flags on accurate fields (deliberate arithmetic errors, document "
        f"ambiguity), counted as neither hits nor false alarms: {fl['explained_flags_on_accurate_fields']}.",
        f"- Missed errors per document: {missed['value']} ({missed['unflagged_errors']} unflagged "
        f"errors / {missed['documents']} documents), of which {fl['errors_in_failed_documents']} "
        "are in documents whose extraction failed (shown to the reviewer as failed).",
        f"- Flags on predicted lines that matched no truth line: {fl['flags_on_unmatched_predicted_lines']}.",
    ]

    rate_groups = [g for g in res["groups"] if not g["case_study"]]
    case_groups = [g for g in res["groups"] if g["case_study"]]
    out += ["", "## Breakdowns (5 or more documents)", ""]
    unscored_notes = [
        f"{g['label']}: {', '.join(g['not_scored'])} not scored."
        for g in rate_groups
        if g.get("not_scored")
    ]
    out += _table(
        ["Group", "Documents", "Layer 1", "Layer 2 strict", "Layer 2 decided", "Line recall", "Flag recall"],
        [
            [g["label"], g["counts"]["documents"], pct(g["counts"]["layer1"]), pct(g["counts"]["layer2_strict"]),
             pct(g["counts"]["layer2_decided"]), pct(g["counts"]["line_recall"]), pct(g["counts"]["flag_recall"])]
            for g in rate_groups
        ],
    )  # fmt: skip
    if unscored_notes:
        out += ["", *unscored_notes]
    out += ["", "## Case studies (groups under 5 documents: counts, no rates)", ""]
    for g in case_groups:
        c, rest = g["counts"], g["rest"]
        unscored = g.get("not_scored") or []
        out += [
            f"### {g['label']} ({', '.join(g['doc_ids'])})",
            "",
            *(
                [f"Not scored (no answer from the model): {', '.join(unscored)}.", ""]
                if unscored
                else []
            ),
            f"Group: layer 1 {counts_only(c['layer1'])} fields, layer 2 {counts_only(c['layer2_strict'])} "
            f"fields, {c['ambiguous']} ambiguous, lines fully right {counts_only(c['line_recall'])}. "
            f"Rest of the set ({rest['documents']} documents): layer 1 {counts_only(rest['layer1'])}, "
            f"layer 2 {counts_only(rest['layer2_strict'])}, lines {counts_only(rest['line_recall'])}.",
            "",
        ]
        out += _table(
            ["Document", "Outcome", "Layer 1", "Layer 2", "Ambiguous", "Lines", "Flags", "Errors"],
            [
                [
                    case["doc_id"], case["outcome"], case["layer1"], case["layer2"], case["ambiguous"],
                    case["lines"], ", ".join(case["flags"]) or "none",
                    "; ".join(f"{e['path']} {e['outcome']} (raw {code(e['raw'])}, printed {code(e['printed'])})"
                              for e in case["errors"]) or "none",
                ]
                for case in g["cases"]
            ],
        )  # fmt: skip
        out.append("")

    out += ["## Error causes (automatic; confirm in error_notes.md)", ""]
    out += _table(
        ["Cause", "Error fields"], [[k, v] for k, v in sorted(res["error_causes"].items())]
    )
    return "\n".join(out) + "\n"


# --- README blocks ---------------------------------------------------------------
# The README's numbers are never typed by hand: these blocks are generated from
# results.json and pasted between markers (python -m eval.report <run> --readme).
# eval/tests/test_readme_numbers.py fails if the README drifts from the file.

README = REPO_ROOT / "README.md"


def _lines_total(case: dict[str, Any]) -> int:
    return int(case["lines"].split(" of ")[1].split()[0])


def readme_blocks(res: dict[str, Any], run_path: str) -> dict[str, str]:
    meta, fields, lines, flags = res["metadata"], res["fields"], res["lines"], res["flags"]
    docs = res["document_accuracy"]
    error_types = [name for name, r in res["per_field"].items() if r["errors"]]
    errors_by_type = ", ".join(f"{res['per_field'][n]['errors']} {n}" for n in error_types)
    amb = fields["ambiguous"]
    results = [
        f"Baseline: one run of `{meta['prompt_version']}` with `{meta['model']}` on the frozen "
        f"{res['status']['documents']}-document test set (commit `{meta['git_commit'][:7]}`, "
        f"metric definitions v{res['metrics_version']}, {coverage_sentence(res)}). It was "
        "recorded before any fix and is the headline result; nothing was tuned on the test "
        f"set. Full report: [`report.md`]({run_path}/report.md), notes: "
        f"[`baseline.md`]({run_path}/baseline.md).",
        "",
        *_table(
            ["Metric", "Result"],
            [
                [
                    "Field accuracy, end to end (layer 2, decided)",
                    f"{pct(fields['layer2_decided'])}, {amb['total']} ambiguous excluded",
                ],
                ["Field accuracy, end to end (layer 2, strict)", pct(fields["layer2_strict"])],
                ["Printed string copied exactly (layer 1)", pct(fields["layer1"])],
                ["Documents with all 9 header fields right", pct(docs["header_only"])],
                ["Documents fully right (header and every line)", pct(docs["full"])],
                ["Line items fully right (recall)", pct(lines["recall"])],
                [
                    "Ambiguous fields (flagged for review)",
                    f"{amb['total']} ({amb['document_ambiguity']} document, "
                    f"{amb['induced_ambiguity']} induced)",
                ],
                ["Errors flagged for review (flag recall)", pct(flags["recall"])],
                ["Review items per document (mean)", flags["review_items_per_document"]["mean"]],
            ],
        ),  # fmt: skip
        "",
        f"Errors by field: {errors_by_type or 'none'}.",
    ]
    sku = next((g for g in res["groups"] if g["key"] == "sku_column"), None)
    item_codes = ""
    if sku:
        wrong = [c for c in sku["cases"] if c["errors"]]
        right = [c["doc_id"] for c in sku["cases"] if not c["errors"]]
        detail = ", ".join(f"{c['doc_id']}: {len(c['errors'])} of {_lines_total(c)}" for c in wrong)
        description = res["per_field"]["description"]
        item_codes = (
            f"Measured on the test-set baseline: {description['errors']} of "
            f"{description['layer2_strict']['d']} line-item descriptions came back as "
            f"`<item code> <description>` ({detail}), and {flags['flagged_error_fields']} of "
            f"{flags['error_fields']} errors were flagged. Item-code tables extracted "
            f"correctly: {', '.join(right) or 'none'} (wrapped descriptions)."
        )
    return {"results": "\n".join(results), "item-codes": item_codes}


def replace_block(text: str, name: str, body: str) -> str:
    """Put ``body`` between the markers, keeping the start marker's indentation
    (so a block inside a list item stays part of that item)."""
    start, end = f"<!-- generated:{name} -->", f"<!-- /generated:{name} -->"
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    newline = "\n"
    indent = before[before.rfind(newline) + 1 :]
    lines = [indent + line if line else line for line in body.split(newline)]
    return f"{before}{start}{newline}" + newline.join(lines) + f"{newline}{indent}{end}{after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.report", description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--readme", action="store_true", help="also rewrite the generated blocks in README.md"
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_dir = args.run_dir if args.run_dir.is_absolute() else REPO_ROOT / args.run_dir
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if args.readme:
        text = README.read_text(encoding="utf-8")
        run_path = run_dir.relative_to(REPO_ROOT).as_posix()
        for name, body in readme_blocks(results, run_path).items():
            text = replace_block(text, name, body)
        README.write_text(text, encoding="utf-8", newline="\n")
        print(f"updated the generated blocks in {README.name}")
        return 0
    report = build_report(results)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
