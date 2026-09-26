"""Scenarios of the removed Phase 1-2 verdict logic, re-expressed against the Phase 3 classifier.

Replaces tests/agents/test_provisional_verdict.py and tests/agents/test_exception_verdict.py.
Each case names the rule that now decides it; cases whose verdict changed say why.
"""

import pytest

from classification.observations import observe
from classification.verdict import surface_outcome

# ---- former provisional_verdict(QAResult) cases ----------------------------------------------------------


def _qa_run(trace, exit_code, results=(), health_ok=True, attempts_failed=0, tool_exc=None):
    qa = trace.agent("qa")
    if tool_exc:
        trace.tool(qa, "pytest", exc=tool_exc)
    else:
        tool = trace.pytest_run(qa, exit_code, results)
        for i in range(attempts_failed):
            trace.span("attempt", tool, exc="ToolTimeoutError", attrs={"qa.retry.attempt": i + 1})
        if attempts_failed:
            trace.span("attempt", tool, attrs={"qa.retry.attempt": attempts_failed + 1})
    trace.health(qa, ok=health_ok)
    return surface_outcome(observe(trace.spans))


@pytest.mark.parametrize(
    "kwargs, verdict, rule",
    [
        (dict(exit_code=0), "PASS", None),
        (dict(exit_code=0, attempts_failed=1), "FLAKY", None),
        (dict(exit_code=1, results=[("t::a", "FAIL", "assert 1 == 2")]), "DEFECT_FOUND", "R11U"),
        (dict(exit_code=1, results=[("t::a", "ERROR", "AttributeError")]), "TEST_BROKEN", "R10"),
        # changed: was TEST_BROKEN (any crash poisoned the run); spec v3 §6.3 puts DEFECT_FOUND first
        (dict(exit_code=1, results=[("t::a", "FAIL", "assert 1 == 2"), ("t::b", "ERROR", "TypeError")]), "DEFECT_FOUND", "R11U"),
        (dict(exit_code=1, results=[("t::a", "ERROR", "fixture 'x' not found")]), "TEST_BROKEN", "R10"),
        (dict(exit_code=2), "TEST_BROKEN", "R8"),
        (dict(exit_code=1, results=[("t::a", "FAIL", "assert 1 == 2")], health_ok=False), "ENV_BLOCKED", "R1"),
        # changed: was ENV_BLOCKED (any tool exception); a runner timing out after retries is HARNESS (R17)
        (dict(exit_code=None, tool_exc="ToolTimeoutError"), "TEST_BROKEN", "R17"),
    ],
)
def test_former_provisional_cases(trace, kwargs, verdict, rule):
    outcome = _qa_run(trace, **kwargs)
    assert outcome.verdict == verdict
    assert (outcome.decided_by.matched_rule if outcome.decided_by else None) == rule


# ---- former exception_verdict(exc) cases --------------------------------------------------------------------


def _llm_failure(trace, exc):
    agent = trace.agent("requirement", exc=exc)
    trace.span("llm.chat", agent, exc=exc)


def _agent_failure(trace, exc):
    trace.agent("automation", exc=exc)


def _tool_failure(trace, exc):
    agent = trace.agent("automation", exc=exc)
    trace.tool(agent, "file_write", exc=exc)


@pytest.mark.parametrize(
    "where, exc, verdict, rule",
    [
        (_llm_failure, "LLMRateLimitError", "ENV_BLOCKED", "R2"),
        (_llm_failure, "LLMUnavailableError", "ENV_BLOCKED", "R3"),
        (_llm_failure, "LLMTimeoutError", "ENV_BLOCKED", "R4"),
        (_llm_failure, "LLMConnectionError", "ENV_BLOCKED", "R4"),
        # changed: was ENV_BLOCKED; no v3 rule covers a bad/missing API key -> UNKNOWN
        (_llm_failure, "LLMConfigError", "INCONCLUSIVE", None),
        # changed: was AGENT_FAILED; a non-provider LLM error (400, empty response) has no v3 rule -> UNKNOWN
        (_llm_failure, "LLMError", "INCONCLUSIVE", None),
        (_agent_failure, "AgentOutputError", "AGENT_FAILED", "R5"),
        (_tool_failure, "UnknownToolError", "AGENT_FAILED", "R6"),
        (_tool_failure, "ToolArgumentError", "AGENT_FAILED", "R6"),
        # changed: was ENV_BLOCKED; a tool (not health check) timing out after retries is R17
        (_tool_failure, "ToolTimeoutError", "TEST_BROKEN", "R17"),
        # changed: was ENV_BLOCKED; only the SUT health check is R1, other connection failures have no rule
        (_tool_failure, "ToolConnectionError", "INCONCLUSIVE", None),
        # changed: was TEST_BROKEN; a generic tool error has no v3 rule -> UNKNOWN
        (_tool_failure, "ToolError", "INCONCLUSIVE", None),
        # changed: was re-raised (crash); an unmatched exception is now UNKNOWN -> INCONCLUSIVE with evidence
        (_agent_failure, "RuntimeError", "INCONCLUSIVE", None),
    ],
)
def test_former_exception_cases(trace, where, exc, verdict, rule):
    where(trace, exc)
    outcome = surface_outcome(observe(trace.spans))
    assert outcome.verdict == verdict
    assert outcome.decided_by.matched_rule == rule
    assert exc in outcome.decided_by.evidence


def test_unmatched_exception_ends_the_run_inconclusive_instead_of_crashing(harness):
    from testing.fake_llm import FakeLLM

    result = harness.run(llm=FakeLLM([RuntimeError("our bug")]))

    assert result.verdict == "INCONCLUSIVE"
    assert result.error == "RuntimeError: our bug"
    root = harness.one("qa.run")
    assert root.attributes["qa.failure.rule"] == "UNKNOWN" and root.attributes["qa.classification.unknown"] == 1
