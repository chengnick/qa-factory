"""SECRET_ACCESS is detected on raw text before redaction, while every stored artifact stays masked;
a generated test that breaks the code policy never runs and the run ends AGENT_FAILED (R18)."""

from __future__ import annotations

import json
from pathlib import Path

from agents.contracts import RequirementInput
from observability.instrument import RunContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import new_instrumentation
from pipeline import run_pipeline
from testing.fake_clock import FakeClock
from testing.fake_llm import FakeLLM
from testing.fake_tool import FakeTool
from tools.file_tool import FileWriteTool
from tools.registry import ToolRegistry, ToolResult
from tools.workspace import create_run_workspace, new_run_id

FAKE_KEY = "AIzaSyA1234567890abcdefghijklmnopqrstuv"
OK = ToolResult(ok=True, exit_code=0, stdout="1 passed", data={"results": []})
HEALTH = ToolResult(ok=True, command="GET /health", data={"method": "GET", "route": "/health", "status_code": 200})


def _llm(test_source: str, requirement_extra: str = "") -> FakeLLM:
    req = {"summary": "s" + requirement_extra, "acceptance_criteria": ["c"]}
    plan = {"cases": [{"id": "TC-1", "title": "t", "surface": "api", "steps": ["s"], "expected": "e"}]}
    files = {"files": [{"path": "generated/test_req005_api.py", "surface": "api", "content": test_source}]}
    return FakeLLM([json.dumps(req), json.dumps(plan), json.dumps(files)])


def _run(tmp_dir: Path, llm: FakeLLM, pytest_tool: FakeTool):
    workspace = create_run_workspace(tmp_dir, new_run_id())
    registry = ToolRegistry()
    registry.register("file_write", FileWriteTool(workspace))
    registry.register("pytest", pytest_tool)
    registry.register("http_request", FakeTool([HEALTH]))
    registry.register("playwright", FakeTool([OK]))
    provider, inst = new_instrumentation(FakeClock(), RunContentSink(workspace), JsonFileSpanExporter(workspace, filename="trace.json"))
    result = run_pipeline(RequirementInput("REQ-005", "text"), llm=llm, tools=registry, inst=inst, run_id=workspace.name, workspace=workspace)
    provider.shutdown()
    return workspace, result


def _all_text(workspace: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in workspace.rglob("*") if p.is_file())


def test_secret_in_llm_output_is_recorded_and_masked_in_artifacts(tmp_dir):
    pytest_tool = FakeTool([OK])
    workspace, result = _run(tmp_dir, _llm("def test_a():\n    assert True\n", requirement_extra=f" key={FAKE_KEY}"), pytest_tool)

    events = [e for e in result.security["events"] if e["type"] == "SECRET_ACCESS"]
    assert len(events) == 1 and events[0]["action"] == "llm.completion"
    assert events[0]["executed"] is False  # masked before it reached any artifact
    assert FAKE_KEY not in json.dumps(result.security)  # the event evidence itself is redacted
    assert FAKE_KEY not in _all_text(workspace)  # prompts/, spans/, trace.json: all masked
    assert result.security["breach"] is False


def test_secret_in_generated_file_is_refused_before_it_is_written(tmp_dir):
    pytest_tool = FakeTool([OK])
    workspace, result = _run(tmp_dir, _llm(f"KEY = '{FAKE_KEY}'\n\ndef test_a():\n    assert True\n"), pytest_tool)

    types = [e["type"] for e in result.security["events"]]
    assert "SECRET_ACCESS" in types
    assert not (workspace / "generated" / "test_req005_api.py").exists()
    assert FAKE_KEY not in _all_text(workspace)
    assert result.verdict == "AGENT_FAILED"
    assert pytest_tool.calls == []


def test_policy_violation_is_never_executed_and_is_agent_failed(tmp_dir):
    pytest_tool = FakeTool([OK])
    source = "import os\n\ndef test_a():\n    os.remove('meta.json')\n"
    workspace, result = _run(tmp_dir, _llm(source), pytest_tool)

    assert pytest_tool.calls == []  # the gate refused before the runner was invoked
    assert result.verdict == "AGENT_FAILED"
    decided = result.classification["surface"]["decided_by"]
    assert (decided["layer"], decided["symptom"], decided["matched_rule"]) == ("AGENT", "PERMISSION_DENIED", "R18")
    (event,) = [e for e in result.security["events"] if e["action"] == "pytest"]
    assert event["type"] == "PERMISSION_DENIED" and event["executed"] is False and "FORBIDDEN_IMPORT import os" in event["evidence"]
