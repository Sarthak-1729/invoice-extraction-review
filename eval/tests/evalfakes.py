"""Shared fakes for the evaluation tests: a scripted provider that answers
with the dev truth's printed strings, a fake git, and a controllable clock."""

import json
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.llm import FakeProvider, LLMError
from eval.sets import get_set, load_truth

DEV = get_set("dev")
DEV_IDS = [f"dev-{i:02d}" for i in range(1, 11)]
TRUTHS = {doc_id: load_truth(DEV, doc_id) for doc_id in DEV_IDS}


def perfect(doc_id):
    t = TRUTHS[doc_id]
    raw = {k: f["printed"] for k, f in t["fields"].items()}
    raw["line_items"] = [{k: f["printed"] for k, f in li.items()} for li in t["line_items"]]
    return raw


class DevModel(FakeProvider):
    """Answers each dev PDF with its truth printed values. ``overrides`` change
    fields; ``failures`` raise an LLMError (a list is consumed one per call;
    a single error repeats); ``texts`` return raw text (e.g. invalid JSON)."""

    def __init__(self):
        super().__init__([self._answer], model="fake-model")
        self.overrides = {}
        self.failures = {}
        self.texts = {}
        self.seen = []

    def _answer(self, system, user):
        doc_id = next(
            d for d, t in TRUTHS.items() if t["fields"]["invoice_number"]["printed"] in user
        )
        self.seen.append(doc_id)
        failure = self.failures.get(doc_id)
        if isinstance(failure, list):
            failure = failure.pop(0) if failure else None
        if isinstance(failure, LLMError):
            raise failure
        if doc_id in self.texts:
            return self.texts[doc_id]
        return json.dumps(perfect(doc_id) | self.overrides.get(doc_id, {}))


def settings():
    return Settings(
        _env_file=None,
        llm_provider="fake",
        llm_transient_retries=0,
        gemini_min_interval_seconds=0,
    )


class FakeGit:
    def __init__(self, head="a" * 40, dirty=None, changed=None):
        self.commit = head
        self.dirty = list(dirty or [])
        self.changed = list(changed or [])

    def head(self):
        return self.commit

    def dirty_files(self):
        return self.dirty

    def changed_since(self, commit):
        return self.changed


class Clock:
    def __init__(self):
        self.moment = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)

    def __call__(self):
        self.moment += timedelta(seconds=1)
        return self.moment

    def advance(self, **kwargs):
        self.moment += timedelta(**kwargs)
