"""Canned fake-mode runs: a FakeLLM script plus fake tools for each scenario.

`flaky` (the default) reproduces the span tree of spec v2 §3.2 (carried over by spec v3 §4.4; text in git history, docs/spec-v2.md @ 639bc1c) exactly:
pytest times out once and passes on attempt 2, then http_request, then playwright.
"""

from __future__ import annotations

import json

from observability.clock import Clock
from testing.fake_llm import FakeLLM
from testing.fake_tool import FakeTool
from tools.registry import ToolRegistry, ToolResult, ToolTimeoutError

SCENARIOS = ("flaky", "pass", "defect")

LLM_LATENCY_S = 1.5
DURATIONS_S = {"file_write": 0.01, "pytest": 3.2, "http_request": 0.05, "playwright": 4.0}


def generated_paths(requirement_id: str) -> tuple[str, str]:
    slug = requirement_id.lower().replace("-", "")
    return f"generated/test_{slug}_api.py", f"generated/test_{slug}_ui.py"


def llm_script(requirement_id: str) -> list[str]:
    api_path, ui_path = generated_paths(requirement_id)
    requirement = {
        "summary": f"Behaviour required by {requirement_id}",
        "acceptance_criteria": ["The API enforces the rule", "The board UI reflects the result"],
    }
    design = {
        "cases": [
            {"id": "TC-1", "title": "API enforces the rule", "surface": "api", "steps": ["call the endpoint"], "expected": "rule enforced"},
            {"id": "TC-2", "title": "UI reflects the result", "surface": "ui", "steps": ["use the board"], "expected": "board updated"},
        ]
    }
    automation = {
        "files": [
            {"path": api_path, "surface": "api", "content": "def test_api_rule():\n    assert True\n"},
            {"path": ui_path, "surface": "ui", "content": "def test_ui_board():\n    assert True\n"},
        ]
    }
    return [json.dumps(requirement), json.dumps(design), "```json\n" + json.dumps(automation) + "\n```"]


def fake_llm(requirement_id: str, clock: Clock | None = None) -> FakeLLM:
    return FakeLLM(llm_script(requirement_id), clock=clock, latency_s=LLM_LATENCY_S if clock else 0.0)


def fake_tools(requirement_id: str, scenario: str = "flaky", clock: Clock | None = None) -> ToolRegistry:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {SCENARIOS}")
    api_path, ui_path = generated_paths(requirement_id)
    pytest_cmd, pw_cmd = f"pytest {api_path}", f"pytest {ui_path} --browser chromium"
    passed = ToolResult(ok=True, exit_code=0, stdout="1 passed in 0.41s", command=pytest_cmd)
    pytest_script: list = {
        "pass": [passed],
        "flaky": [ToolTimeoutError("pytest did not finish within 60s"), passed],
        "defect": [ToolResult(ok=False, exit_code=1, command=pytest_cmd, stdout="E   AssertionError: expected 409, got 200\n1 failed in 0.52s")],
    }[scenario]

    def tool(script: list, name: str) -> FakeTool:
        return FakeTool(script, clock=clock, duration_s=DURATIONS_S[name] if clock else 0.0)

    registry = ToolRegistry()
    registry.register("file_write", tool([ToolResult(ok=True, command="file_write")], "file_write"))
    registry.register("pytest", tool(pytest_script, "pytest"))
    registry.register(
        "http_request",
        tool([ToolResult(ok=True, command="GET /health", data={"method": "GET", "route": "/health", "status_code": 200})], "http_request"),
    )
    registry.register("playwright", tool([ToolResult(ok=True, exit_code=0, stdout="1 passed in 2.10s", command=pw_cmd)], "playwright"))
    return registry
