"""dev_check with the fake provider only: resume, skip, stop rules, dev-only."""

import json

import pytest

from app import dev_check
from app.config import Settings
from app.dev_check import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_STOPPED_QUOTA,
    MAX_INFRA_RUNS,
    RESULTS_ROOT,
    DevCheckError,
    build_report,
    dev_documents,
    run_documents,
)
from app.llm import FakeProvider, LLMError, LLMErrorCode
from app.testset_guard import REPO_ROOT

DEV = REPO_ROOT / "eval" / "datasets" / "dev"
TRUTHS = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((DEV / "truth").glob("*.json"))
}
SETTINGS = Settings(_env_file=None, llm_provider="fake", llm_transient_retries=0)


def doc_for(user_message):
    for doc_id, t in TRUTHS.items():
        if t["fields"]["invoice_number"]["printed"] in user_message:
            return doc_id
    raise AssertionError("unknown document")


def perfect_json(doc_id, tweak=None):
    t = TRUTHS[doc_id]
    raw = {k: f["printed"] for k, f in t["fields"].items()}
    raw["line_items"] = [{k: f["printed"] for k, f in i.items()} for i in t["line_items"]]
    if tweak:
        tweak(doc_id, raw)
    return json.dumps(raw)


class ScriptedModel(FakeProvider):
    """Perfect answers, except documents mapped to an error."""

    def __init__(self, errors=None, tweak=None):
        self.errors = errors or {}
        self.seen = []
        super().__init__([self._answer])
        self._tweak = tweak

    def _answer(self, system, user):
        doc_id = doc_for(user)
        self.seen.append(doc_id)
        if doc_id in self.errors:
            raise self.errors[doc_id]
        return perfect_json(doc_id, self._tweak)


def run(tmp_path, model, **kwargs):
    lines = []
    code, run_dir = run_documents(SETTINGS, model, out_root=tmp_path, echo=lines.append, **kwargs)
    return code, run_dir, lines


def test_results_go_to_a_git_ignored_folder():
    assert RESULTS_ROOT.relative_to(REPO_ROOT).parts[0] == "data"
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/" in gitignore


def test_only_dev_documents_are_used():
    pdfs = dev_documents()
    assert [p.stem for p in pdfs] == [f"dev-{n:02d}" for n in range(1, 11)]
    assert all(p.parent == DEV / "pdf" for p in pdfs)
    with pytest.raises(DevCheckError):
        dev_documents(["test-01"])


def test_full_run_then_resume_skips_everything(tmp_path):
    model = ScriptedModel()
    code, run_dir, _ = run(tmp_path, model)
    assert code == EXIT_OK and len(model.seen) == 10
    record = json.loads((run_dir / "dev-01.json").read_text(encoding="utf-8"))
    assert record["outcome"] == "success" and record["metrics_version"] == "1.1"
    assert record["prompt_hash"] and record["pdf_sha256"]

    again = ScriptedModel()
    code, _, lines = run(tmp_path, again)
    assert code == EXIT_OK and again.seen == []
    assert all("skip" in line for line in lines)


def test_report_lists_only_differing_fields(tmp_path):
    def tweak(doc_id, raw):
        if doc_id == "dev-01":
            raw["total"] = "$1.00"

    _, run_dir, _ = run(tmp_path, ScriptedModel(tweak=tweak))
    report = build_report(run_dir)
    diff_section = report.split("## Fields that differ")[1]
    assert "| dev-01 | total |" in diff_section
    assert "| dev-03 | currency | yes | ambiguous |" in diff_section  # $-only document
    assert diff_section.count("\n| dev-") == 2  # nothing else differs


def test_infrastructure_failure_is_retried_on_later_runs_up_to_n(tmp_path):
    unavailable = LLMError(LLMErrorCode.UNAVAILABLE, "503 high demand")
    for run_number in range(1, MAX_INFRA_RUNS + 1):
        model = ScriptedModel(errors={"dev-09": unavailable})
        code, run_dir, _ = run(tmp_path, model)
        assert code == EXIT_OK  # other documents are not blocked
        assert "dev-09" in model.seen
        record = json.loads((run_dir / "dev-09.json").read_text(encoding="utf-8"))
        assert record["outcome"] == "infrastructure_failure"
        assert record["infra_runs"] == run_number

    capped = ScriptedModel()
    _, run_dir, lines = run(tmp_path, capped)
    assert capped.seen == []
    assert any("never succeeded after 3 runs" in line for line in lines)
    assert "not scored: infrastructure" in build_report(run_dir)

    forced = ScriptedModel()
    run(tmp_path, forced, retry_infra=True)
    assert forced.seen == ["dev-09"]


def test_quota_exhaustion_stops_the_run_and_resumes_later(tmp_path):
    quota = LLMError(LLMErrorCode.RATE_LIMITED, "daily quota", retry_after=3600)
    model = ScriptedModel(errors={"dev-03": quota})
    code, run_dir, lines = run(tmp_path, model)
    assert code == EXIT_STOPPED_QUOTA
    assert model.seen == ["dev-01", "dev-02", "dev-03"]  # stopped at the first sign
    assert "Stopping: rate limit or quota" in lines[-1]

    later = ScriptedModel()
    code, _, _ = run(tmp_path, later)
    assert code == EXIT_OK
    assert later.seen == [f"dev-{n:02d}" for n in range(3, 11)]  # dev-01 and 02 skipped


def test_configuration_error_stops(tmp_path):
    model = ScriptedModel(errors={"dev-01": LLMError(LLMErrorCode.AUTH_FAILED, "bad key")})
    code, _, lines = run(tmp_path, model)
    assert code == EXIT_CONFIG and model.seen == ["dev-01"]
    assert "configuration error" in lines[-1]


def test_model_failure_is_recorded_and_not_rerun(tmp_path):
    class BadJsonForDev02(ScriptedModel):
        def _answer(self, system, user):
            if doc_for(user) == "dev-02":
                self.seen.append("dev-02")
                return "not json"
            return super()._answer(system, user)

    _, run_dir, _ = run(tmp_path, BadJsonForDev02())
    record = json.loads((run_dir / "dev-02.json").read_text(encoding="utf-8"))
    assert record["outcome"] == "model_failure"
    assert record["result"]["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    again = ScriptedModel()
    run(tmp_path, again)
    assert again.seen == []
    assert "| dev-02 | model_failure |" in build_report(run_dir)


def test_unexpected_errors_do_not_stop_the_run(tmp_path, monkeypatch):
    real = dev_check.run_pipeline

    def flaky(pdf, *args):
        if pdf.stem == "dev-04":
            raise RuntimeError("boom")
        return real(pdf, *args)

    monkeypatch.setattr(dev_check, "run_pipeline", flaky)
    code, run_dir, _ = run(tmp_path, ScriptedModel())
    assert code == EXIT_OK
    record = json.loads((run_dir / "dev-04.json").read_text(encoding="utf-8"))
    assert record["result"]["error"]["code"] == "UNEXPECTED_ERROR"
    assert (run_dir / "dev-10.json").exists()
    assert json.loads((run_dir / "dev-10.json").read_text(encoding="utf-8"))["outcome"] == "success"


def test_cli_rejects_unknown_documents(capsys, monkeypatch):
    monkeypatch.setattr(dev_check, "Settings", lambda **kw: Settings(_env_file=None, **kw))
    code = dev_check.main(["--only", "test-01", "--provider", "fake"])
    assert code == EXIT_CONFIG
    assert "Not dev documents" in capsys.readouterr().out


def test_candidate_prompt_runs_only_when_named(tmp_path):
    from app.prompt import load_prompt

    model = ScriptedModel()
    _, default_dir, _ = run(tmp_path, model, only=["dev-01"])
    assert default_dir.name.endswith(load_prompt().sha256[:12])
    assert "extraction_v2" in default_dir.name

    candidate = ScriptedModel()
    _, candidate_dir, _ = run(tmp_path, candidate, only=["dev-01"], prompt_version="extraction_v4")
    assert "extraction_v4" in candidate_dir.name and candidate_dir != default_dir
    assert load_prompt("extraction_v4").system in candidate.calls[0]["system"]
    record = json.loads((candidate_dir / "dev-01.json").read_text(encoding="utf-8"))
    assert record["prompt_version"] == "extraction_v4"
    assert record["result"]["prompt_hash"] == load_prompt("extraction_v4").sha256


@pytest.mark.parametrize("version", ["extraction_v99", "../extraction_v2", "v2"])
def test_unknown_prompt_versions_are_rejected(tmp_path, version):
    with pytest.raises(DevCheckError):
        run(tmp_path, ScriptedModel(), only=["dev-01"], prompt_version=version)
