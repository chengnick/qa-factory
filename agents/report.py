from __future__ import annotations

from agents.base import AgentDeps, AgentOutputError
from agents.contracts import QAResult, Report, Verdict
from llm.client import (
    LLMConfigError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from tools.registry import ToolArgumentError, ToolConnectionError, ToolError, ToolTimeoutError, UnknownToolError

RUNNERS = ("pytest", "playwright")

# Verdict for an exception that aborted the pipeline, by exception type (first match wins).
# PROVISIONAL until classification/ lands in Phase 3.
EXCEPTION_VERDICTS: tuple[tuple[tuple[type[BaseException], ...], Verdict], ...] = (
    # The LLM provider or the SUT could not serve the run: nothing was learned about the SUT.
    ((LLMRateLimitError, LLMUnavailableError), "ENV_BLOCKED"),  # 429 / 503
    ((LLMTimeoutError, LLMConnectionError, LLMConfigError), "ENV_BLOCKED"),  # unreachable, bad or missing key
    ((ToolTimeoutError, ToolConnectionError), "ENV_BLOCKED"),
    # The agent produced something unusable: bad output, a handoff missing fields, a bad tool call.
    ((AgentOutputError, UnknownToolError, ToolArgumentError), "AGENT_FAILED"),
    ((LLMError,), "AGENT_FAILED"),  # any other LLM failure, e.g. empty/blocked response or 400
    # A tool broke for another reason (harness): the run's result cannot be trusted.
    ((ToolError,), "TEST_BROKEN"),
)


def exception_verdict(exc: BaseException) -> Verdict | None:
    """Verdict for an exception that aborted the run; None if the type is not classified (a bug in our code)."""
    for types, verdict in EXCEPTION_VERDICTS:
        if isinstance(exc, types):
            return verdict
    return None


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
