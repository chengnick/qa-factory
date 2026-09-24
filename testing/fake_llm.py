"""Scripted LLM: returns (or raises) the scripted items in order. No network, no randomness."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from llm.client import ChatResponse, Message
from observability.clock import Clock

ScriptItem = str | ChatResponse | BaseException


class ScriptExhaustedError(AssertionError):
    """The code under test made more LLM calls than the script anticipated."""


@dataclass
class FakeCall:
    messages: tuple[Message, ...]


class FakeLLM:
    def __init__(
        self,
        script: Iterable[ScriptItem],
        model: str = "fake-model",
        *,
        tokens_per_char: float | None = 0.25,
        clock: Clock | None = None,
        latency_s: float = 0.0,
    ) -> None:
        self._script = list(script)
        self._clock = clock
        self.latency_s = latency_s
        self.model = model
        self.tokens_per_char = tokens_per_char
        self.calls: list[FakeCall] = []

    @property
    def remaining(self) -> int:
        return len(self._script)

    def chat(self, messages: Sequence[Message]) -> ChatResponse:
        self.calls.append(FakeCall(tuple(messages)))
        if self._clock is not None and self.latency_s:
            self._clock.sleep(self.latency_s)
        if not self._script:
            raise ScriptExhaustedError(f"FakeLLM script exhausted after {len(self.calls) - 1} call(s)")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, ChatResponse):
            return item
        return ChatResponse(item, self.model, *self._usage(messages, item))

    def _usage(self, messages: Sequence[Message], output: str) -> tuple[int | None, int | None]:
        if self.tokens_per_char is None:
            return None, None
        prompt_chars = sum(len(m.content) for m in messages)
        return max(1, round(prompt_chars * self.tokens_per_char)), max(1, round(len(output) * self.tokens_per_char))
