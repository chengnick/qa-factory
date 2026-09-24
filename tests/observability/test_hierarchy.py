"""The span tree of a fake run matches spec 3.2, rebuilt purely from parent_span_id links."""

from opentelemetry.trace import StatusCode

EXPECTED_FLAKY_TREE = (
    "qa.run",
    (
        ("agent.requirement", (("llm.chat", ()),)),
        ("agent.test_design", (("llm.chat", ()),)),
        ("agent.automation", (("llm.chat", ()), ("tool.file_write", ()), ("tool.file_write", ()))),
        (
            "agent.qa",
            (
                ("tool.pytest", (("attempt", ()), ("attempt", ()))),
                ("tool.http_request", ()),
                ("tool.playwright", (("attempt", ()),)),
            ),
        ),
        ("agent.report", ()),
    ),
)


def test_flaky_run_matches_spec_tree(harness):
    result = harness.run(scenario="flaky")

    assert result.error is None
    assert harness.tree() == EXPECTED_FLAKY_TREE


def test_all_spans_share_one_trace(harness):
    result = harness.run()

    trace_ids = {format(s.context.trace_id, "032x") for s in harness.spans()}
    assert trace_ids == {result.trace_id}


def test_single_attempt_tools_have_no_attempt_children(harness):
    harness.run(scenario="pass")

    assert harness.children(harness.one("tool.http_request")) == []
    for span in harness.named("tool.file_write"):
        assert harness.children(span) == []
    assert [c.name for c in harness.children(harness.one("tool.pytest"))] == ["attempt"]


def test_agent_failure_still_produces_complete_tree(harness):
    from testing.fake_llm import FakeLLM

    result = harness.run(llm=FakeLLM(["not json"]))

    assert result.verdict == "AGENT_FAILED"
    assert harness.tree() == ("qa.run", (("agent.requirement", (("llm.chat", ()),)),))
    root, agent = harness.one("qa.run"), harness.one("agent.requirement")
    assert root.status.status_code is StatusCode.ERROR
    assert agent.status.status_code is StatusCode.ERROR
    assert "AgentOutputError" in agent.status.description
