"""Durations come from the injected FakeClock only, so they are exact."""

import pytest

from observability.instrument import TracedToolRegistry, start_span
from testing.fake_clock import DEFAULT_START_NS, FakeClock
from testing.fake_tool import FakeTool
from tools.registry import RetryPolicy, ToolRegistry, ToolResult, ToolTimeoutError

NS = 1_000_000_000


def _duration_s(span):
    return (span.end_time - span.start_time) / NS


def test_span_duration_equals_clock_advance(harness):
    with start_span(harness.inst, "work"):
        harness.clock.advance(3.2)

    span = harness.one("work")
    assert span.start_time == DEFAULT_START_NS
    assert _duration_s(span) == pytest.approx(3.2, abs=1e-9)


def test_retry_durations_include_backoff_between_attempts(harness):
    registry = ToolRegistry()
    registry.register(
        "pytest",
        FakeTool([ToolTimeoutError("slow"), ToolResult(ok=True, exit_code=0)], clock=harness.clock, duration_s=3.0),
        retry=RetryPolicy(max_attempts=3, backoff_s=1.5),
    )

    TracedToolRegistry(registry, harness.inst).call("pytest", paths=["generated/test_x.py"])

    first, second = sorted(harness.named("attempt"), key=lambda s: s.attributes["qa.retry.attempt"])
    assert _duration_s(first) == pytest.approx(3.0)
    assert _duration_s(second) == pytest.approx(3.0)
    assert (second.start_time - first.end_time) / NS == pytest.approx(1.5)  # backoff sits between attempts
    assert _duration_s(harness.one("tool.pytest")) == pytest.approx(7.5)


def test_full_run_duration_is_deterministic(harness):
    harness.run(scenario="flaky")

    # 3 LLM calls x 1.5s + 2 file writes x 0.01s + pytest (3.2 + 1.0 backoff + 3.2) + http 0.05 + playwright 4.0
    assert _duration_s(harness.one("qa.run")) == pytest.approx(4.5 + 0.02 + 7.4 + 0.05 + 4.0)
    assert _duration_s(harness.one("agent.report")) == 0


def test_same_run_twice_gives_identical_timings():
    from observability.instrument import Instrumentation, MemoryContentSink
    from observability.setup import create_tracer_provider, get_tracer
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from agents.contracts import RequirementInput
    from pipeline import run_pipeline
    from testing import scripts

    def timings():
        exporter, clock = InMemorySpanExporter(), FakeClock()
        provider = create_tracer_provider(exporter)
        inst = Instrumentation(get_tracer(provider), clock, MemoryContentSink())
        run_pipeline(RequirementInput("REQ-005", "t"), llm=scripts.fake_llm("REQ-005", clock), tools=scripts.fake_tools("REQ-005", "flaky", clock), inst=inst)
        return [(s.name, s.start_time, s.end_time) for s in exporter.get_finished_spans()]

    assert timings() == timings()


def test_fake_clock_never_goes_backwards():
    with pytest.raises(ValueError):
        FakeClock().advance(-1)
