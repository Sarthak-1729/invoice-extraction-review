"""Scripted provider for tests and offline runs. Makes no network calls."""

from collections.abc import Callable, Iterable
from typing import Any

from app.llm.base import LLMError, LLMResponse

Step = str | LLMError | Callable[[str, str], str]


class FakeProvider:
    """Returns the scripted steps in order (JSON text, an error to raise, or a
    function of (system, user)); the last step repeats. Records every call."""

    name = "fake"

    def __init__(self, steps: Iterable[Step] = ("{}",), model: str = "fake-model") -> None:
        self.steps = list(steps)
        if not self.steps:
            raise ValueError("FakeProvider needs at least one step")
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema": schema})
        step = self.steps[min(len(self.calls), len(self.steps)) - 1]
        if isinstance(step, LLMError):
            raise step
        text = step(system, user) if callable(step) else step
        return LLMResponse(text=text)
