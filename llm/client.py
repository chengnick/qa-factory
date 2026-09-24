"""LLM client interface. Agents depend on this Protocol only; concrete clients are injected."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ChatResponse:
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(Protocol):
    model: str

    def chat(self, messages: Sequence[Message]) -> ChatResponse: ...


class LLMError(Exception):
    """Base class for errors raised by an LLM client."""


class LLMRateLimitError(LLMError):
    """The provider rejected the request with HTTP 429."""


class LLMTimeoutError(LLMError):
    """The provider did not answer in time."""
