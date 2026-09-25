"""Attribute naming per spec v2 §3.3 (carried over by spec v3 §4.4; text in git history, docs/spec-v2.md @ 639bc1c) and spec v3 §4.4: gen_ai.* on LLM/tool spans, qa.* namespace, verdict placement."""

import pytest
from opentelemetry.trace import StatusCode


def test_root_carries_run_attributes(harness):
    harness.run(requirement_id="REQ-005", sut_bugs=("B02",))

    root = harness.one("qa.run")
    assert root.attributes["qa.run.requirement_id"] == "REQ-005"
    assert tuple(root.attributes["qa.run.sut_bugs"]) == ("B02",)
    assert root.attributes["qa.verdict"] == "FLAKY"


def test_verdict_only_on_root_and_qa_agent(harness):
    harness.run()

    carriers = sorted(s.name for s in harness.spans() if "qa.verdict" in s.attributes)
    assert carriers == ["agent.qa", "qa.run"]


@pytest.mark.parametrize("scenario, verdict", [("pass", "PASS"), ("flaky", "FLAKY"), ("defect", "DEFECT_FOUND")])
def test_provisional_verdict_per_scenario(harness, scenario, verdict):
    result = harness.run(scenario=scenario)

    assert result.verdict == verdict
    assert harness.one("agent.qa").attributes["qa.verdict"] == verdict


def test_agent_spans_name_their_agent(harness):
    harness.run()

    for span in harness.spans():
        if span.name.startswith("agent."):
            assert span.attributes["qa.agent.name"] == span.name.removeprefix("agent.")


def test_llm_spans_follow_genai_conventions(harness):
    harness.run()

    llm_spans = harness.named("llm.chat")
    assert len(llm_spans) == 3
    for span in llm_spans:
        assert span.attributes["gen_ai.operation.name"] == "chat"
        assert span.attributes["gen_ai.request.model"] == "fake-model"
        assert span.attributes["gen_ai.usage.input_tokens"] > 0
        assert span.attributes["gen_ai.usage.output_tokens"] > 0
        assert [e.name for e in span.events] == ["prompt", "completion"]


def test_gen_ai_usage_only_on_llm_spans(harness):
    harness.run()

    for span in harness.spans():
        if any(k.startswith("gen_ai.usage.") for k in span.attributes):
            assert span.name == "llm.chat"


def test_tool_spans_carry_tool_attributes(harness):
    harness.run()

    for span in harness.spans():
        if span.name.startswith("tool."):
            name = span.name.removeprefix("tool.")
            assert span.attributes["qa.tool.name"] == name
            assert span.attributes["gen_ai.tool.name"] == name
            assert span.attributes["gen_ai.operation.name"] == "execute_tool"
    pytest_span = harness.one("tool.pytest")
    assert pytest_span.attributes["qa.tool.command"].startswith("pytest generated/")
    assert pytest_span.attributes["qa.tool.exit_code"] == 0


def test_http_attributes(harness):
    harness.run()

    span = harness.one("tool.http_request")
    assert span.attributes["qa.http.method"] == "GET"
    assert span.attributes["qa.http.route"] == "/health"
    assert span.attributes["qa.http.status_code"] == 200


def test_failed_tool_result_marks_tool_and_attempt_error(harness):
    harness.run(scenario="defect")

    span = harness.one("tool.pytest")
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description == "1 failed in 0.52s"
    assert span.attributes["qa.tool.exit_code"] == 1
    (attempt,) = harness.children(span)
    assert attempt.status.status_code is StatusCode.ERROR
    tail = next(e for e in span.events if e.name == "stdout.tail")
    assert "AssertionError: expected 409, got 200" in tail.attributes["text"]


def test_large_content_is_truncated_in_event_and_kept_in_artifact(harness):
    from testing.fake_tool import FakeTool
    from tools.registry import ToolRegistry, ToolResult

    big = "x" * 5000 + "TAIL"
    tools = ToolRegistry()
    tools.register("file_write", FakeTool([ToolResult(ok=True)]))
    tools.register("pytest", FakeTool([ToolResult(ok=True, exit_code=0, stdout=big)]))
    tools.register("http_request", FakeTool([ToolResult(ok=True)]))
    tools.register("playwright", FakeTool([ToolResult(ok=True, exit_code=0)]))

    harness.run(tools=tools)

    span = harness.one("tool.pytest")
    event = next(e for e in span.events if e.name == "stdout.tail")
    assert event.attributes["truncated"] is True
    assert event.attributes["length"] == len(big)
    assert len(event.attributes["text"]) == 2000 and event.attributes["text"].endswith("TAIL")
    stored = [v for (t, s, kind), v in harness.sink.items.items() if kind == "stdout" and s == format(span.context.span_id, "016x")]
    assert stored == [big]
    assert "artifact" in event.attributes
