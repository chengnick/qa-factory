"""with_retry(): one attempt span per try, bounded, only for retryable errors."""

import pytest
from opentelemetry.trace import StatusCode

from llm.client import LLMRateLimitError, Message
from observability.instrument import TracedLLM, TracedToolRegistry, start_span, with_retry
from testing.fake_llm import FakeLLM
from testing.fake_tool import FakeTool
from tools.registry import RetryPolicy, ToolRegistry, ToolResult, ToolTimeoutError, UnknownToolError

OK = ToolResult(ok=True, exit_code=0, stdout="1 passed")
POLICY = RetryPolicy(max_attempts=3, backoff_s=1.0)


def _tools(script, policy=POLICY):
    registry = ToolRegistry()
    tool = FakeTool(script)
    registry.register("pytest", tool, retry=policy)
    return registry, tool


def _attempts(harness):
    return sorted(harness.named("attempt"), key=lambda s: s.attributes["qa.retry.attempt"])


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_n_timeouts_then_success_gives_n_plus_one_attempts(harness, failures):
    registry, tool = _tools([ToolTimeoutError("slow")] * failures + [OK])

    result = TracedToolRegistry(registry, harness.inst).call("pytest", paths=["x"])

    attempts = _attempts(harness)
    assert [a.attributes["qa.retry.attempt"] for a in attempts] == list(range(1, failures + 2))
    assert [a.status.status_code for a in attempts] == [StatusCode.ERROR] * failures + [StatusCode.OK]
    assert all(a.attributes["qa.failure.symptom"] == "TIMEOUT" for a in attempts[:failures])
    assert all(a.parent.span_id == harness.one("tool.pytest").context.span_id for a in attempts)
    assert result.attempts == failures + 1 and len(tool.calls) == failures + 1
    assert harness.one("tool.pytest").status.status_code is StatusCode.OK


def test_persistent_timeout_stops_at_max_attempts(harness):
    registry, tool = _tools([ToolTimeoutError("slow")])

    with pytest.raises(ToolTimeoutError) as exc_info:
        TracedToolRegistry(registry, harness.inst).call("pytest")

    assert len(tool.calls) == 3
    assert len(_attempts(harness)) == 3
    assert exc_info.value.attempts == 3
    tool_span = harness.one("tool.pytest")
    assert tool_span.status.status_code is StatusCode.ERROR
    assert tool_span.attributes["qa.failure.symptom"] == "TIMEOUT"


def test_non_retryable_error_is_a_single_attempt(harness):
    registry, tool = _tools([RuntimeError("boom"), OK])

    with pytest.raises(RuntimeError):
        TracedToolRegistry(registry, harness.inst).call("pytest")

    assert len(tool.calls) == 1
    (attempt,) = _attempts(harness)
    assert attempt.status.status_code is StatusCode.ERROR


def test_failed_result_is_final_not_retried(harness):
    registry, tool = _tools([ToolResult(ok=False, exit_code=1, stdout="1 failed"), OK])

    result = TracedToolRegistry(registry, harness.inst).call("pytest")

    assert not result.ok and result.attempts == 1 and len(tool.calls) == 1
    (attempt,) = _attempts(harness)
    assert attempt.status.status_code is StatusCode.ERROR
    assert attempt.status.description == "1 failed"


def test_backoff_is_exponential_and_goes_through_the_clock(harness):
    registry, _ = _tools([ToolTimeoutError("slow")])

    with pytest.raises(ToolTimeoutError):
        TracedToolRegistry(registry, harness.inst).call("pytest")

    assert harness.clock.sleeps == [1.0, 2.0]


def test_single_attempt_policy_emits_no_attempt_spans(harness):
    registry, _ = _tools([ToolTimeoutError("slow")], policy=RetryPolicy(max_attempts=1))

    with pytest.raises(ToolTimeoutError):
        TracedToolRegistry(registry, harness.inst).call("pytest")

    assert harness.named("attempt") == []
    assert harness.one("tool.pytest").status.status_code is StatusCode.ERROR


def test_llm_rate_limit_retry_emits_attempts_under_llm_span(harness):
    llm = FakeLLM([LLMRateLimitError("429"), '{"ok": true}'])
    traced = TracedLLM(llm, harness.inst, RetryPolicy(max_attempts=3, retry_on=(LLMRateLimitError,), backoff_s=2.0))

    response = traced.chat([Message("user", "hi")])

    assert response.content == '{"ok": true}'
    attempts = _attempts(harness)
    assert [a.status.status_code for a in attempts] == [StatusCode.ERROR, StatusCode.OK]
    assert attempts[0].attributes["qa.failure.symptom"] == "RATE_LIMIT"
    assert all(a.parent.span_id == harness.one("llm.chat").context.span_id for a in attempts)
    assert harness.clock.sleeps == [2.0]


def test_unknown_tool_is_recorded_not_executed(harness):
    registry, tool = _tools([OK])

    with pytest.raises(UnknownToolError):
        TracedToolRegistry(registry, harness.inst).call("rm_rf")

    span = harness.one("tool.rm_rf")
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["qa.failure.symptom"] == "INVALID_OUTPUT"
    assert tool.calls == []


def test_with_retry_nests_under_current_span(harness):
    with start_span(harness.inst, "outer") as outer:
        outcome = with_retry(lambda: 42, POLICY, harness.inst)

    assert outcome.value == 42 and outcome.attempts == 1
    (attempt,) = _attempts(harness)
    assert attempt.parent.span_id == outer.get_span_context().span_id


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
