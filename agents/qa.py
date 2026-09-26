from __future__ import annotations

from typing import Any

from agents.base import AgentDeps, HandoffError
from agents.contracts import AutomationResult, QAResult, ToolExecution
from tools.registry import ToolError


class QAAgent:
    """Runs the generated tests. No LLM: execution is deterministic."""

    name = "qa"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, automation: AutomationResult) -> QAResult:
        if not automation.files:
            raise HandoffError("automation", "no generated test files")
        api = [f.path for f in automation.files if f.surface == "api"]
        ui = [f.path for f in automation.files if f.surface == "ui"]
        executions = []
        if api:
            executions.append(self._execute("pytest", paths=api))
        # Probe the SUT after the API run, so a dead SUT is not mistaken for a failing assertion.
        executions.append(self._execute("http_request", method="GET", route="/health"))
        if ui:
            executions.append(self._execute("playwright", paths=ui))
        return QAResult(automation.requirement_id, tuple(executions))

    def _execute(self, tool: str, **args: Any) -> ToolExecution:
        try:
            result = self.deps.tools.call(tool, **args)
        except ToolError as exc:
            attempts = getattr(exc, "attempts", 1)
            return ToolExecution(tool, ok=False, attempts=attempts, error=f"{type(exc).__name__}: {exc}")
        lines = result.stdout.strip().splitlines()
        return ToolExecution(tool, result.ok, result.attempts, result.exit_code, lines[-1] if lines else "", data=dict(result.data))
