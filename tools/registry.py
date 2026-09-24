"""Tool registry: the only way agents reach tools.

Phase 1 scope: registration, lookup, per-tool retry policy. Parameter schema validation
and permission checks are added in Phase 2 / Phase 5.

This registry never retries by itself. Retries happen only in observability's
`with_retry()`, which records every attempt as a span (no silent retries).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
    """A tool could not produce a result."""


class ToolTimeoutError(ToolError):
    """A tool did not finish in time. Retryable by default."""


class UnknownToolError(ToolError):
    """The requested tool is not registered."""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    exit_code: int | None = None
    stdout: str = ""
    command: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_on: tuple[type[BaseException], ...] = (ToolTimeoutError,)
    backoff_s: float = 0.0  # delay before attempt n+1 is backoff_s * 2**(n-1)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")


NO_RETRY = RetryPolicy()
# Test runners are the tools that time out transiently; see spec 3.2.
DEFAULT_POLICIES: dict[str, RetryPolicy] = {
    "pytest": RetryPolicy(max_attempts=3, backoff_s=1.0),
    "playwright": RetryPolicy(max_attempts=3, backoff_s=1.0),
}

ToolFn = Callable[..., ToolResult]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    fn: ToolFn
    retry: RetryPolicy


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, fn: ToolFn, retry: RetryPolicy | None = None) -> None:
        if name in self._tools:
            raise ValueError(f"tool {name!r} already registered")
        self._tools[name] = RegisteredTool(name, fn, retry or DEFAULT_POLICIES.get(name, NO_RETRY))

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(f"tool {name!r} is not registered") from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, **args: Any) -> ToolResult:
        """Single attempt, no tracing. Pipelines use observability.TracedToolRegistry instead."""
        return self.get(name).fn(**args)
