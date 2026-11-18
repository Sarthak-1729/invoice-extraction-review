"""Metrics, error analysis and report on fake-provider runs of the DEV set."""

import json
import re
from types import SimpleNamespace

import pytest

from app.llm import LLMError, LLMErrorCode
from eval.metrics import (
    MetricsError,
    _group_definitions,
    compute,
    oracle_ambiguous_paths,
    write_outputs,
)
from eval.report import build_report
from eval.run_test import Options, run_evaluation
from eval.sets import document_ids, get_set, load_truth
from eval.tests.evalfakes import DEV, TRUTHS, Clock, DevModel, FakeGit, perfect, settings


def run_dev(tmp_path, model, clock=None, **options):
    clock = clock or Clock()
    _, run_dir = run_evaluation(
        DEV, model, settings(), Options(**options), results_root=tmp_path / "results",
        git=FakeGit(), now=clock, echo=lambda _: None,
    )  # fmt: skip
    return run_dir


@pytest.fixture(scope="module")
def perfect_run(tmp_path_factory):
    run_dir = run_dev(tmp_path_factory.mktemp("perfect"), DevModel())
    return run_dir, compute(run_dir)


def test_a_perfect_extractor_scores_100_with_ambiguity_split_out(perfect_run):
    _, computed = perfect_run
    res = computed["results"]
    f = res["fields"]
    assert res["status"]["complete"] and res["status"]["scored"] == 10
    assert f["errors"] == 0
    assert f["layer1"]["n"] == f["layer1"]["d"] == f["field_instances"]
    assert f["layer2_decided"]["pct"] == 100.0
    # Every ambiguous field of a perfect extractor is document ambiguity.
    assert f["ambiguous"]["induced_ambiguity"] == 0
    assert f["layer2_strict"]["n"] == f["field_instances"] - f["ambiguous"]["total"]
    assert res["lines"]["recall"]["pct"] == res["lines"]["precision"]["pct"] == 100.0
    assert res["flags"]["false_alarms"] == 0  # no flag on an accurate field went unexplained
    assert res["flags"]["error_fields"] == 0
    assert res["arithmetic"]["consistent_valid"]["pct"] == 100.0
    assert all(c["expected_fired"] for c in res["arithmetic"]["deliberate_cases"])


def test_counts_are_always_stored_with_percentages(perfect_run):
    def walk(node):
        if isinstance(node, dict):
            if "pct" in node:
                assert {"n", "d"} <= set(node), node
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(perfect_run[1]["results"])


def test_metadata_recorded_in_results(perfect_run):
    meta = perfect_run[1]["results"]["metadata"]
    assert meta["set_sha256"] == DEV.expected_sha256
    for key in ("model", "settings", "prompt_version", "prompt_hash", "git_commit", "git_dirty",
                "created", "metrics_version", "provider"):  # fmt: skip
        assert key in meta


def test_errors_flags_and_causes(tmp_path):
    model = DevModel()
    wrong_total = "$999.99"
    model.overrides["dev-01"] = {"total": wrong_total}  # wrong at both layers, not in the PDF
    model.overrides["dev-02"] = {"vendor_name": None}  # missing (flagged: required field)
    vendor = TRUTHS["dev-03"]["fields"]["vendor_name"]["printed"]
    model.overrides["dev-03"] = {"bill_to_name": vendor}  # misplaced: in the PDF, so unflagged
    model.texts["dev-04"] = "not json"  # schema failure -> model failure
    run_dir = run_dev(tmp_path, model)
    computed = compute(run_dir)
    res, analysis = computed["results"], computed["analysis"]

    assert res["status"]["model_failures"] == ["dev-04"]
    o = res["fields"]["outcomes"]
    assert o["wrong"] >= 1 and o["missing"] >= 1 + 9  # dev-02 vendor + dev-04 header
    by_key = {(e["doc_id"], e["path"]): e for e in analysis["field_errors"]}
    total = by_key[("dev-01", "total")]
    assert total["outcome"] == "wrong" and "TOTAL_MISMATCH" in total["flags"]
    assert "VALUE_NOT_IN_DOCUMENT" in total["flags"]
    assert total["auto_cause"] == "extraction"
    assert by_key[("dev-02", "vendor_name")]["flags"] == ["REQUIRED_FIELD_MISSING"]
    misplaced = by_key[("dev-03", "bill_to_name")]
    assert misplaced["outcome"] == "wrong" and misplaced["flags"] == []  # an unflagged miss
    assert res["flags"]["missed_errors_per_document"]["unflagged_errors"] >= 1 + 9
    assert by_key[("dev-04", "invoice_number")]["auto_cause"] == "schema_failure"
    fl = res["flags"]
    assert fl["recall"]["d"] == fl["error_fields"] and fl["recall"]["n"] >= 1
    assert fl["errors_in_failed_documents"] == 9
    assert fl["missed_errors_per_document"]["documents"] == 10


def test_normalization_cause(tmp_path):
    run_dir = run_dev(tmp_path, DevModel())
    computed = compute(run_dir)
    # Simulate a normalizer mistake: layer 1 right, layer 2 wrong.
    record_path = run_dir / "predictions.jsonl"
    lines = [json.loads(line) for line in record_path.read_text("utf-8").splitlines()]
    lines[0]["result"]["normalized"]["invoice_date"] = "1999-01-01"
    record_path.write_text("".join(json.dumps(r) + "\n" for r in lines), "utf-8")
    analysis = compute(run_dir)["analysis"]
    error = next(e for e in analysis["field_errors"] if e["path"] == "invoice_date")
    assert error["layer1"] is True and error["auto_cause"] == "normalization"
    assert computed["results"]["fields"]["errors"] == 0


def test_never_succeeded_documents_are_excluded_and_a_worst_case_is_given(tmp_path):
    model = DevModel()
    model.failures["dev-06"] = LLMError(LLMErrorCode.UNAVAILABLE, "503")
    clock = Clock()
    run_dev(tmp_path, model, clock)
    for _ in range(2):
        clock.advance(minutes=31)
        run_dir = run_dev(tmp_path, model, clock, next_run=True)
    res = compute(run_dir)["results"]
    assert res["status"]["never_succeeded_infrastructure"] == ["dev-06"]
    assert res["status"]["complete"] and res["status"]["scored"] == 9
    worst = res["layer2_strict_worst_case"]
    assert worst["d"] == res["fields"]["field_instances"] + 9
    assert res["documents"]["dev-06"]["history"] == [
        {"run": n, "outcome": "infrastructure_failure", "error_code": "LLM_UNAVAILABLE"}
        for n in (1, 2, 3)
    ]
    report = build_report(res)
    assert "never succeeded (infrastructure)" in report and "dev-06" in report
    # dev-06 stays in its groups, listed as not scored (never silently dropped).
    groups_with_it = [g for g in res["groups"] if "dev-06" in g["doc_ids"]]
    assert groups_with_it and all(g["not_scored"] == ["dev-06"] for g in groups_with_it)
    assert (
        "Not scored (no answer from the model): dev-06." in report or "dev-06 not scored" in report
    )


def test_report_tables_have_plain_cells(perfect_run):
    report = build_report(perfect_run[1]["results"])
    assert "| [" not in report and "['" not in report
    assert "| description accuracy over matched lines | 100.0% (" in report


def test_pending_retries_mark_the_results_incomplete(tmp_path):
    model = DevModel()
    model.failures["dev-06"] = [LLMError(LLMErrorCode.UNAVAILABLE, "503")]
    res = compute(run_dev(tmp_path, model))["results"]
    assert not res["status"]["complete"]
    assert res["status"]["pending_infrastructure_retry"] == ["dev-06"]
    assert "Incomplete run" in build_report(res)


def test_a_configuration_error_makes_the_run_invalid(tmp_path):
    model = DevModel()
    model.failures["dev-01"] = [LLMError(LLMErrorCode.AUTH_FAILED, "401")]
    run_dir = run_dev(tmp_path, model)
    with pytest.raises(MetricsError, match="not valid"):
        compute(run_dir)


def test_error_notes_are_created_once_and_never_overwritten(perfect_run, tmp_path):
    run_dir, computed = perfect_run
    write_outputs(run_dir, computed)
    notes = run_dir / "error_notes.md"
    notes.write_text("my confirmed causes\n", "utf-8")
    write_outputs(run_dir, computed)
    assert notes.read_text("utf-8") == "my confirmed causes\n"
    assert json.loads((run_dir / "results.json").read_text("utf-8"))["metrics_version"] == "1.1"


def test_report_has_counts_next_to_every_percentage_and_no_rates_for_small_groups(perfect_run):
    report = build_report(perfect_run[1]["results"])
    for match in re.finditer(r"\d+\.\d%", report):
        after = report[match.end() : match.end() + 30]
        line = report[report.rfind("\n", 0, match.start()) + 1 : report.find("\n", match.end())]
        assert after.startswith(" (") or line.startswith("| F1"), line
    case_part = report.split("## Case studies")[1].split("## Error causes")[0]
    assert "%" not in case_part
    assert "### " in case_part  # the dev set has small groups (e.g. the arithmetic one)


def test_groups_follow_the_size_rule(perfect_run):
    groups = perfect_run[1]["results"]["groups"]
    for g in groups:
        assert g["case_study"] == (len(g["doc_ids"]) < 5), g["key"]
        if g["case_study"]:
            assert len(g["cases"]) == len(g["doc_ids"])
            assert g["rest"]["documents"] == 10 - len(g["doc_ids"])


def test_test_set_groups_match_the_documented_slices():
    """Reads only the test set's truth metadata (features and printed strings
    for the oracle); nothing is extracted."""
    test = get_set("test")
    docs = []
    for doc_id in document_ids(test):
        truth = load_truth(test, doc_id)
        docs.append(
            SimpleNamespace(
                doc_id=doc_id,
                truth=truth,
                features=truth["features"],
                oracle_ambiguous=oracle_ambiguous_paths(truth),
            )
        )
    groups = {key: ids for key, _, ids in _group_definitions(docs)}
    t = lambda *n: [f"test-{i:02d}" for i in n]  # noqa: E731
    assert groups["sku_column"] == t(19, 20, 22, 24)
    assert groups["wrapped_descriptions"] == t(4, 22)
    assert groups["injection"] == t(3, 9)
    assert groups["arith_error"] == t(3, 8, 16, 20)
    assert groups["ambiguity"] == t(2, 17, 22)
    assert len(groups["currency:JPY"]) == 3 and len(groups["currency:CAD"]) == 2
    assert len(groups["currency:other"]) == 19
    assert len(groups["numbers:plain"]) == 1 and len(groups["amount_before_qty"]) == 2
    assert all(
        len(groups[f"layout:{n}"]) == 6 for n in ("classic_us", "european", "modern", "multipage")
    )


def test_oracle_marks_a_dollar_only_currency_as_document_ambiguity():
    truth = TRUTHS["dev-03"]
    assert truth["fields"]["currency"]["printed"] == "$"
    assert "currency" in oracle_ambiguous_paths(truth)
    assert perfect("dev-03")["currency"] == "$"
