"""Trace -> classification units -> verdicts (surface and cross-validated)."""

from classification.observations import observe
from classification.verdict import final_outcome, surface_outcome


def _qa(trace):
    return trace.agent("qa")


def test_clean_run_has_no_units(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 0)
    trace.health(qa)
    obs = observe(trace.spans)
    assert obs.surface == [] and surface_outcome(obs).verdict == "PASS"


def test_assertion_failures_become_per_test_units_and_surface_defect(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 1, [("t.py::a", "FAIL", "assert 200 == 409"), ("t.py::b", "ERROR", "AttributeError: x")])
    trace.health(qa)
    outcome = surface_outcome(observe(trace.spans))
    assert sorted(c.matched_rule for c in outcome.classifications) == ["R10", "R11U"]
    assert outcome.verdict == "DEFECT_FOUND" and outcome.decided_by.unverified


def test_retried_away_failure_marks_flaky_not_a_unit(trace):
    qa = _qa(trace)
    tool = trace.tool(qa, "pytest", attrs={"qa.tool.exit_code": 0})
    trace.span("attempt", tool, exc="ToolTimeoutError", attrs={"qa.retry.attempt": 1})
    trace.span("attempt", tool, attrs={"qa.retry.attempt": 2})
    obs = observe(trace.spans)
    assert obs.surface == [] and obs.flaky
    assert surface_outcome(obs).verdict == "FLAKY"


def test_agent_unit_only_when_the_failure_started_in_the_agent(trace):
    automation = trace.agent("automation", exc="AgentOutputError", error="not valid JSON")
    trace.span("llm.chat", automation)
    design = trace.agent("test_design", exc="LLMRateLimitError")
    trace.span("llm.chat", design, exc="LLMRateLimitError")
    kinds = sorted(u.kind for u in observe(trace.spans).surface)
    assert kinds == ["agent", "llm"]  # the rate-limited agent span is not a second unit


def test_health_probe_failure_is_env(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 1, [("t.py::a", "ERROR", "httpx.ConnectError")])
    trace.health(qa, exc="ToolConnectionError")
    outcome = surface_outcome(observe(trace.spans))
    assert outcome.verdict == "ENV_BLOCKED" and outcome.decided_by.matched_rule == "R1"


def test_collection_error_is_one_tool_unit(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 2, [("generated/test_x.py", "ERROR", "collection failure")])
    (unit,) = observe(trace.spans).surface
    assert unit.kind == "tool" and unit.collection_error


def test_playwright_health_context_reaches_test_units(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 1, [("t.py::ui", "ERROR", "TimeoutError: Locator.click: Timeout 5000ms exceeded")], tool="playwright")
    trace.health(qa)
    assert surface_outcome(observe(trace.spans)).decided_by.matched_rule == "R14"


def _differential(*decisions, status="COMPLETE"):
    return {"status": status, "decisions": [{"node_id": n, "bug_outcome": b, "decision": d, "rule": r, "evidence": e} for n, b, d, r, e in decisions]}


def test_cross_validation_replaces_qa_test_units(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 1, [("t.py::a", "FAIL", "assert 200 == 409"), ("t.py::b", "FAIL", "assert 1 == 2")])
    trace.health(qa)
    diff = _differential(("t.py::a", "FAIL", "DETECTED", "R11", "bug build: assert 200 == 409"),
                         ("t.py::b", "FAIL", "BROKEN", "R12", "fails on a clean SUT"),
                         ("t.py::c", "PASS", "NOT_DETECTED", None, ""))  # fmt: skip
    obs = observe(trace.spans, differential=diff)
    final = final_outcome(obs, bugs_enabled=True)
    assert sorted(c.matched_rule for c in final.classifications) == ["R11", "R12"]
    assert final.verdict == "DEFECT_FOUND" and not final.decided_by.unverified


def test_missed_when_cross_validation_finds_nothing(trace):
    qa = _qa(trace)
    trace.pytest_run(qa, 0)
    trace.health(qa)
    obs = observe(trace.spans, differential=_differential(("t.py::a", "PASS", "NOT_DETECTED", None, "")))
    assert final_outcome(obs, bugs_enabled=True).verdict == "MISSED"
    assert final_outcome(obs, bugs_enabled=False).verdict == "PASS"


def test_unhealthy_evaluation_build_is_env(trace):
    diff_span = trace.span("evaluation.differential", trace.root, error="ENV_BLOCKED")
    trace.span("evaluation.build", diff_span, error="health check failed", attrs={"qa.failure.rule": "R1", "qa.failure.layer": "ENV"})
    obs = observe(trace.spans, differential={"status": "ENV_BLOCKED", "decisions": []})
    final = final_outcome(obs, bugs_enabled=True)
    assert final.verdict == "ENV_BLOCKED" and final.decided_by.matched_rule == "R1"


def test_build_runner_exit_codes_are_not_units_but_timeouts_are(trace):
    diff_span = trace.span("evaluation.differential", trace.root)
    build = trace.span("evaluation.build", diff_span)
    trace.pytest_run(build, 1, [("t.py::a", "FAIL", "assert 1 == 2")])
    trace.tool(build, "playwright", exc="ToolTimeoutError")
    obs = observe(trace.spans)
    assert obs.surface == [] and [u.exception for u in obs.evaluation] == ["ToolTimeoutError"]


def test_tampered_cross_validation_is_inconclusive(trace):
    obs = observe(trace.spans, differential={"status": "TAMPERED", "reason": "generated test files changed", "decisions": []})
    assert final_outcome(obs, bugs_enabled=True).verdict == "INCONCLUSIVE"


def test_old_traces_use_junit_fallback_for_test_results(trace):
    """Phase 2R traces predate qa.test.result events; results come from the run's junit reports."""
    qa = _qa(trace)
    tool = trace.tool(qa, "pytest", error="1 failed", attrs={"qa.tool.exit_code": 1})
    trace.health(qa)
    fallback = {tool["span_id"]: [{"node_id": "t.py::a", "outcome": "FAIL", "message": "assert 200 == 409"}]}
    outcome = surface_outcome(observe(trace.spans, test_results_fallback=fallback))
    assert outcome.decided_by.matched_rule == "R11U"
