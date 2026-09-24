from __future__ import annotations

from agents.base import AgentDeps
from agents.contracts import QAResult, Report, Verdict


def provisional_verdict(qa: QAResult) -> Verdict:
    """PROVISIONAL (Phase 1). Replaced by classification/verdict.py in Phase 3.

    Tool raised -> ENV_BLOCKED; any failed result -> DEFECT_FOUND; retried then passed -> FLAKY.
    """
    if any(e.error for e in qa.executions):
        return "ENV_BLOCKED"
    if any(not e.ok for e in qa.executions):
        return "DEFECT_FOUND"
    if any(e.attempts > 1 for e in qa.executions):
        return "FLAKY"
    return "PASS"


class ReportAgent:
    name = "report"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, qa: QAResult) -> Report:
        verdict = provisional_verdict(qa)
        lines = [f"{qa.requirement_id}: {verdict}"]
        for e in qa.executions:
            status = "ok" if e.ok else "FAILED"
            detail = e.error or e.summary
            suffix = f" - {detail}" if detail else ""
            lines.append(f"- {e.tool}: {status} (attempts={e.attempts}, exit={e.exit_code}){suffix}")
        return Report(qa.requirement_id, verdict, "\n".join(lines))
