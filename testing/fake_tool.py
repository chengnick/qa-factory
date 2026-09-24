"""Scripted tool (Phase 1 minimum; extended in Phase 3).

Each call consumes the next scripted item: a ToolResult is returned, an exception is raised.
When the script runs out, the last item repeats (so "always times out" is a one-item script).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from observability.clock import Clock
from tools.registry import ToolResult

ScriptItem = ToolResult | BaseException


class FakeTool:
    def __init__(self, script: Iterable[ScriptItem], *, clock: Clock | None = None, duration_s: float = 0.0) -> None:
        self._script = list(script)
        if not self._script:
            raise ValueError("FakeTool needs at least one scripted item")
        self._clock = clock
        self.duration_s = duration_s
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **args: Any) -> ToolResult:
        self.calls.append(args)
        if self._clock is not None and self.duration_s:
            self._clock.sleep(self.duration_s)
        item = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        if isinstance(item, BaseException):
            raise type(item)(*item.args)  # fresh instance: a repeated item must not share traceback/state
        return item
