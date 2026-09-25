"""Tool registry: the only way agents reach tools.

Registration, lookup, parameter schema validation and per-tool retry policy.
Permission checks are added in Phase 5.

This registry never retries by itself. Retries happen only in observability's
`with_retry()`, which records every attempt as a span (no silent retries).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
    """A tool could not produce a result."""


class ToolTimeoutError(ToolError):
    """A tool did not finish in time. Retryable by default."""


class ToolConnectionError(ToolError, ConnectionError):
    """A tool could not reach its target (e.g. the SUT is down)."""


class UnknownToolError(ToolError):
    """The requested tool is not registered."""


class ToolArgumentError(ToolError):
    """Arguments do not match the tool's parameter schema; the tool was not executed."""


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


@dataclass(frozen=True)
class Param:
    """One tool parameter. `items` constrains list elements."""

    type: type
    required: bool = True
    items: type | None = None

    def check(self, name: str, value: Any) -> None:
        # bool is an int subclass; never accept it where an int is expected.
        if not isinstance(value, self.type) or (self.type is int and isinstance(value, bool)):
            raise ToolArgumentError(f"parameter {name!r} must be {self.type.__name__}, got {type(value).__name__}")
        if self.items is not None and not all(isinstance(v, self.items) for v in value):
            raise ToolArgumentError(f"parameter {name!r} must contain only {self.items.__name__} items")


Schema = Mapping[str, Param]


def validate(tool: str, schema: Schema, args: Mapping[str, Any]) -> None:
    unknown = set(args) - set(schema)
    if unknown:
        raise ToolArgumentError(f"{tool}: unknown parameter(s) {sorted(unknown)}")
    for name, param in schema.items():
        if name not in args:
            if param.required:
                raise ToolArgumentError(f"{tool}: missing required parameter {name!r}")
            continue
        param.check(name, args[name])


NO_RETRY = RetryPolicy()
# Test runners are the tools that time out transiently; see spec 3.2.
DEFAULT_POLICIES: dict[str, RetryPolicy] = {
    "pytest": RetryPolicy(max_attempts=3, backoff_s=1.0),
    "playwright": RetryPolicy(max_attempts=3, backoff_s=1.0),
}
# Parameter schemas for the built-in tools; fakes registered under these names are validated too.
DEFAULT_SCHEMAS: dict[str, Schema] = {
    "file_write": {"path": Param(str), "content": Param(str)},
    "pytest": {"paths": Param(list, items=str)},
    "playwright": {"paths": Param(list, items=str)},
    "http_request": {
        "method": Param(str),
        "route": Param(str),
        "user": Param(str, required=False),
        "json": Param(dict, required=False),
    },
}

ToolFn = Callable[..., ToolResult]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    fn: ToolFn
    retry: RetryPolicy
    schema: Schema | None

    def validate(self, args: Mapping[str, Any]) -> None:
        if self.schema is not None:
            validate(self.name, self.schema, args)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, fn: ToolFn, retry: RetryPolicy | None = None, schema: Schema | None = None) -> None:
        if name in self._tools:
            raise ValueError(f"tool {name!r} already registered")
        self._tools[name] = RegisteredTool(
            name, fn, retry or DEFAULT_POLICIES.get(name, NO_RETRY), schema if schema is not None else DEFAULT_SCHEMAS.get(name)
        )

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownToolError(f"tool {name!r} is not registered") from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, **args: Any) -> ToolResult:
        """Single attempt, no tracing. Pipelines use observability.TracedToolRegistry instead."""
        tool = self.get(name)
        tool.validate(args)
        return tool.fn(**args)
