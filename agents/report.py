from __future__ import annotations

from agents.base import AgentDeps, HandoffError
from agents.contracts import QAResult, Report


class ReportAgent:
    """Summarises the QA executions. It does not decide the verdict: classification/ derives that from the trace,
    so nothing an LLM writes (e.g. an injected "mark every test PASS") can change it."""

    name = "report"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, qa: QAResult) -> Report:
        if not qa.executions:
            raise HandoffError("qa", "no tool executions to report")
        lines = [f"{qa.requirement_id}: {len(qa.executions)} tool execution(s)"]
        for e in qa.executions:
            status = "ok" if e.ok else "FAILED"
            detail = e.error or e.summary
            suffix = f" - {detail}" if detail else ""
            lines.append(f"- {e.tool}: {status} (attempts={e.attempts}, exit={e.exit_code}){suffix}")
        return Report(qa.requirement_id, "\n".join(lines))
