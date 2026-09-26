"""Shared agent plumbing. Agents get the LLM and tools injected; they never build clients."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from llm.client import LLMClient, Message
from tools.registry import ToolResult

In = TypeVar("In", contravariant=True)
Out = TypeVar("Out", covariant=True)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class Tools(Protocol):
    def call(self, name: str, **args: Any) -> ToolResult: ...


@dataclass(frozen=True)
class AgentDeps:
    llm: LLMClient
    tools: Tools


class Agent(Protocol[In, Out]):
    name: str

    def run(self, inp: In) -> Out: ...


class AgentOutputError(Exception):
    """The LLM output does not have the expected structure."""


class HandoffError(AgentOutputError):
    """A downstream agent rejected its input: the upstream agent's output is missing required content.

    The failure is attributed to `upstream` (spec v3 R7), not to the agent that detected it.
    """

    def __init__(self, upstream: str, message: str) -> None:
        super().__init__(f"handoff from {upstream} rejected: {message}")
        self.upstream = upstream


def ask_json(llm: LLMClient, system: str, user: str) -> dict[str, Any]:
    response = llm.chat([Message("system", system), Message("user", user)])
    text = response.content.strip()
    if m := _FENCE.match(text):
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"LLM output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentOutputError(f"LLM output must be a JSON object, got {type(data).__name__}")
    return data


def field(data: dict[str, Any], key: str, typ: type) -> Any:
    value = data.get(key)
    if not isinstance(value, typ):
        raise AgentOutputError(f"field {key!r} must be {typ.__name__}, got {type(value).__name__}")
    return value


def str_list(data: dict[str, Any], key: str) -> tuple[str, ...]:
    items = field(data, key, list)
    if not all(isinstance(i, str) for i in items):
        raise AgentOutputError(f"field {key!r} must be a list of strings")
    return tuple(items)


def dict_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = field(data, key, list)
    if not all(isinstance(i, dict) for i in items):
        raise AgentOutputError(f"field {key!r} must be a list of objects")
    return items
