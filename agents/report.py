from __future__ import annotations

from agents.base import AgentDeps
from agents.contracts import QAResult, Report, Verdict


RUNNERS = ("pytest", "playwright")


def provisional_verdict(qa: QAResult) -> Verdict:
    """PROVISIONAL (Phase 1-2). Replaced by classification/verdict.py in Phase 3.

    In order: a tool raised or the SUT health probe failed -> ENV_BLOCKED; the test run itself broke
    (pytest exit code other than 0/1, setup/collection errors, or test code raising something other than
    AssertionError) -> TEST_BROKEN; an assertion failed -> DEFECT_FOUND; a retry changed the outcome ->
    FLAKY; otherwise PASS. An assertion failure caused by a wrong test still counts as DEFECT_FOUND here;
    telling those apart needs the reference-test cross-check (rules R8/R9, Phase 3).
    """
    if any(e.error for e in qa.executions):
        return "ENV_BLOCKED"
    if any(e.tool == "http_request" and not e.ok for e in qa.executions):
        return "ENV_BLOCKED"
    runs = [e for e in qa.executions if e.tool in RUNNERS]
    if any(e.exit_code not in (0, 1, None) or e.data.get("errors", 0) > 0 or e.data.get("exception_failures", 0) > 0 for e in runs):
        return "TEST_BROKEN"
    if any(not e.ok for e in runs):
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
