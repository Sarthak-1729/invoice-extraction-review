"""The evaluation runner, with the fake provider on the DEV set only.

The test set is never extracted here: the refusal tests stop before any
provider call, and every run uses eval/datasets/dev.
"""

import json
import shutil
from dataclasses import replace

import pytest

from app.llm import LLMError, LLMErrorCode
from eval import run_test
from eval.run_test import (
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_STOPPED,
    Options,
    RunRefused,
    read_predictions,
    run_evaluation,
)
from eval.sets import EvalSetError, get_set
from eval.tests.evalfakes import DEV, DEV_IDS, Clock, DevModel, FakeGit, settings


@pytest.fixture
def model():
    return DevModel()


@pytest.fixture
def clock():
    return Clock()


def run(tmp_path, model, clock, git=None, eval_set=DEV, **options):
    lines = []
    code, run_dir = run_evaluation(
        eval_set,
        model,
        settings(),
        Options(**options),
        results_root=tmp_path / "results",
        git=git or FakeGit(),
        now=clock,
        echo=lines.append,
    )
    return code, run_dir, lines


def records(run_dir):
    return read_predictions(run_dir / "predictions.jsonl")


# --- refusals -------------------------------------------------------------------


def test_held_out_set_is_refused_without_the_flag(tmp_path, model, clock):
    with pytest.raises(RunRefused, match="--allow-test-set"):
        run(tmp_path, model, clock, eval_set=get_set("test"))
    assert model.calls == []
    assert not (tmp_path / "results").exists()


def test_cli_refuses_without_the_flag_before_building_a_provider(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setattr(run_test, "get_provider", lambda s: pytest.fail("provider built"))
    assert run_test.main([]) == EXIT_REFUSED
    assert "Pass --allow-test-set" in capsys.readouterr().out


def test_cli_refuses_a_provider_other_than_gemini_or_another_model(monkeypatch, capsys):
    monkeypatch.setattr(run_test, "get_provider", lambda s: pytest.fail("provider built"))
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert run_test.main(["--allow-test-set"]) == EXIT_REFUSED
    assert "evaluation uses gemini" in capsys.readouterr().out
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-other")
    assert run_test.main(["--allow-test-set"]) == EXIT_REFUSED
    assert "expected 'gemini-3.5-flash-lite'" in capsys.readouterr().out


def test_dirty_tree_is_refused(tmp_path, model, clock):
    git = FakeGit(dirty=["backend/app/prompt.py"])
    with pytest.raises(RunRefused, match="not clean.*backend/app/prompt.py"):
        run(tmp_path, model, clock, git=git)
    assert model.calls == []


def test_dirty_tree_override_is_recorded(tmp_path, model, clock):
    git = FakeGit(dirty=["notes.txt"])
    code, run_dir, _ = run(tmp_path, model, clock, git=git, allow_dirty=True)
    meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    assert code == EXIT_OK
    assert meta["git_dirty"] is True and meta["dirty_files"] == ["notes.txt"]


def test_changed_set_files_are_refused_before_any_call(tmp_path, model, clock):
    copy = tmp_path / "dev"
    shutil.copytree(DEV.directory, copy)
    truth = copy / "truth" / "dev-01.json"
    truth.write_text(truth.read_text("utf-8").replace("INV", "XNV", 1), "utf-8")
    with pytest.raises(EvalSetError, match="files differ"):
        run(tmp_path, model, clock, eval_set=replace(DEV, directory=copy))
    (copy / "MANIFEST.sha256").write_text("", "utf-8")
    with pytest.raises(EvalSetError, match="manifest hash"):
        run(tmp_path, model, clock, eval_set=replace(DEV, directory=copy))
    assert model.calls == []


def test_hand_made_set_does_not_exist_yet():
    with pytest.raises(EvalSetError, match="no recorded hash"):
        from eval.sets import verify

        verify(get_set("handmade"))


# --- a full run and resuming ------------------------------------------------------


def test_full_dev_run_records_metadata_and_one_line_per_document(tmp_path, model, clock):
    code, run_dir, lines = run(tmp_path, model, clock)
    assert code == EXIT_OK
    assert run_dir.parent.name == "dev" and run_dir.name.startswith("fake-model__extraction_v4__")
    recs = records(run_dir)
    assert [r["doc_id"] for r in recs] == DEV_IDS
    assert {r["outcome"] for r in recs} == {"success"} and {r["run_number"] for r in recs} == {1}
    meta = json.loads((run_dir / "run.json").read_text("utf-8"))
    for key in ("provider", "model", "settings", "prompt_version", "prompt_hash", "git_commit",
                "git_dirty", "created", "set_sha256", "metrics_version"):  # fmt: skip
        assert key in meta, key
    assert meta["set_sha256"] == DEV.expected_sha256 and meta["metrics_version"] == "1.1"
    assert meta["git_dirty"] is False
    assert meta["settings"]["llm_transient_retries"] == 0
    assert meta["runs"][0]["documents"] == DEV_IDS and meta["runs"][0]["ended"]

    calls = len(model.calls)
    code, _, lines = run(tmp_path, model, clock)  # rerun: nothing redone
    assert code == EXIT_OK and len(model.calls) == calls
    assert "Nothing to do" in lines[-1]


def test_quota_stop_resumes_without_redoing_finished_documents(tmp_path, model, clock):
    model.failures["dev-04"] = [LLMError(LLMErrorCode.RATE_LIMITED, "429 quota")]
    code, run_dir, lines = run(tmp_path, model, clock)
    assert code == EXIT_STOPPED and "quota" in lines[-2]
    assert [r["doc_id"] for r in records(run_dir)] == DEV_IDS[:4]
    assert records(run_dir)[-1]["outcome"] == "infrastructure_failure"

    code, _, _ = run(tmp_path, model, clock)  # resume run 1: only documents never attempted
    assert code == EXIT_OK
    assert model.seen == DEV_IDS  # dev-04 once (it waits for run 2), nothing twice
    assert {r["run_number"] for r in records(run_dir)} == {1}


def test_infrastructure_failures_wait_for_the_next_run_and_30_minutes(tmp_path, model, clock):
    model.failures["dev-02"] = [LLMError(LLMErrorCode.UNAVAILABLE, "503 high demand")]
    run(tmp_path, model, clock)
    code, run_dir, lines = run(tmp_path, model, clock)  # no --next-run
    assert code == EXIT_OK and "Retry them in run 2 with --next-run" in lines[-1]
    with pytest.raises(RunRefused, match="30 minutes"):
        run(tmp_path, model, clock, next_run=True)
    clock.advance(minutes=31)
    code, _, _ = run(tmp_path, model, clock, next_run=True)
    assert code == EXIT_OK
    recs = records(run_dir)
    assert [(r["doc_id"], r["run_number"], r["outcome"]) for r in recs[-1:]] == [
        ("dev-02", 2, "success")
    ]
    assert model.seen.count("dev-02") == 2 and model.seen.count("dev-01") == 1


def test_never_more_than_three_runs(tmp_path, model, clock):
    model.failures["dev-03"] = LLMError(LLMErrorCode.TIMEOUT, "timed out")  # always
    run(tmp_path, model, clock)
    for _ in range(2):
        clock.advance(minutes=31)
        run(tmp_path, model, clock, next_run=True)
    clock.advance(minutes=31)
    code, run_dir, lines = run(tmp_path, model, clock, next_run=True)
    assert code == EXIT_OK and "Nothing to do" in lines[-1]
    assert model.seen.count("dev-03") == 3
    runs = json.loads((run_dir / "run.json").read_text("utf-8"))["runs"]
    assert [r["documents"] for r in runs[1:]] == [["dev-03"], ["dev-03"]]


def test_next_run_is_refused_while_the_current_run_is_unfinished(tmp_path, model, clock):
    model.failures["dev-01"] = [LLMError(LLMErrorCode.RATE_LIMITED, "429")]
    run(tmp_path, model, clock)  # stops after dev-01
    clock.advance(hours=1)
    with pytest.raises(RunRefused, match="not finished"):
        run(tmp_path, model, clock, next_run=True)


def test_configuration_error_stops_and_the_document_is_tried_again(tmp_path, model, clock):
    model.failures["dev-01"] = [LLMError(LLMErrorCode.AUTH_FAILED, "401 bad key")]
    code, run_dir, lines = run(tmp_path, model, clock)
    assert code == EXIT_STOPPED and "configuration error" in lines[-2]
    assert records(run_dir)[0]["outcome"] == "configuration_error"
    code, _, _ = run(tmp_path, model, clock)  # "fixed": same run, dev-01 again
    assert code == EXIT_OK
    assert [r["outcome"] for r in records(run_dir) if r["doc_id"] == "dev-01"] == [
        "configuration_error",
        "success",
    ]


def test_bad_request_after_successes_is_a_model_failure(tmp_path, model, clock):
    model.failures["dev-03"] = LLMError(LLMErrorCode.BAD_REQUEST, "400 too many states")
    code, run_dir, _ = run(tmp_path, model, clock)
    assert code == EXIT_OK
    rec = next(r for r in records(run_dir) if r["doc_id"] == "dev-03")
    assert rec["outcome"] == "model_failure" and "other documents" in rec["note"]


def test_schema_failure_is_a_model_failure_and_never_rerun(tmp_path, model, clock):
    model.texts["dev-05"] = "not json"
    run(tmp_path, model, clock)
    rec = next(r for r in records(run_dir_of(tmp_path)) if r["doc_id"] == "dev-05")
    assert (rec["outcome"], rec["error_code"]) == ("model_failure", "SCHEMA_VALIDATION_FAILED")
    clock.advance(hours=1)
    code, _, lines = run(tmp_path, model, clock, next_run=True)
    assert "Nothing to do" in lines[-1]


def run_dir_of(tmp_path):
    return next((tmp_path / "results" / "dev").iterdir())


def test_a_torn_last_line_is_cut_off_and_the_document_redone(tmp_path, model, clock):
    model.failures["dev-03"] = [LLMError(LLMErrorCode.RATE_LIMITED, "429")]
    _, run_dir, _ = run(tmp_path, model, clock)  # dev-01..03 written
    path = run_dir / "predictions.jsonl"
    path.write_bytes(path.read_bytes() + b'{"doc_id": "dev-04", "run_nu')  # crash mid-write
    run(tmp_path, model, clock)
    assert path.read_bytes().count(b'"dev-04"') == 1
    assert [r["doc_id"] for r in records(run_dir)] == DEV_IDS


# --- same run, same code ------------------------------------------------------------


def test_resume_refuses_changed_settings_or_code(tmp_path, model, clock):
    model.failures["dev-02"] = [LLMError(LLMErrorCode.RATE_LIMITED, "429")]
    run(tmp_path, model, clock)
    with pytest.raises(RunRefused, match="code changed"):
        run(
            tmp_path, model, clock, git=FakeGit(head="b" * 40, changed=["backend/app/normalize.py"])
        )
    code, _, _ = run(
        tmp_path, model, clock, git=FakeGit(head="b" * 40, changed=["eval/results/test/x/run.json"])
    )
    assert code == EXIT_OK  # committing results only is fine

    other = settings().model_copy(update={"llm_transient_retries": 5})
    with pytest.raises(RunRefused, match="Settings changed"):
        run_evaluation(DEV, model, other, Options(), results_root=tmp_path / "results",
                       git=FakeGit(), now=clock, echo=lambda _: None)  # fmt: skip
