"""Shared helpers for the deterministic fault-injection harness: fake LLM/provider/tools, a real gate and FileWriteTool in a temp workspace.

No SUT, no network, no real LLM; time is a FakeClock (retry backoff costs nothing).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents.contracts import RequirementInput
from observability.instrument import RunContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import new_instrumentation
from pipeline import PipelineResult, run_pipeline
from testing.fake_clock import FakeClock
from testing.fake_llm import FakeLLM
from testing.fake_tool import FakeTool
from tools.file_tool import FileWriteTool
from tools.registry import RetryPolicy, ToolRegistry, ToolResult
from tools.workspace import create_run_workspace, new_run_id

PASSED = ToolResult(ok=True, exit_code=0, stdout="1 passed", command="pytest", data={"results": []})
HEALTHY = ToolResult(ok=True, command="GET /health", data={"method": "GET", "route": "/health", "status_code": 200})
API_TEST = "import pytest\n\n\ndef test_a(as_user):\n    assert as_user('alice') is not None\n"


def llm_script(files: list[dict] | None = None, criteria: list[str] | None = None) -> list[str]:
    requirement = {"summary": "done is terminal", "acceptance_criteria": criteria if criteria is not None else ["done -> in_progress is 409"]}
    plan = {"cases": [{"id": "TC-1", "title": "t", "surface": "api", "steps": ["s"], "expected": "409"}]}
    files = files if files is not None else [{"path": "generated/test_req005_api.py", "surface": "api", "content": API_TEST}]
    return [json.dumps(requirement), json.dumps(plan), json.dumps({"files": files})]


@dataclass
class Scenario:
    result: PipelineResult
    exporter: InMemorySpanExporter
    workspace: Path
    tools: dict[str, FakeTool]

    def spans(self, name: str | None = None) -> list[Any]:
        return [s for s in self.exporter.get_finished_spans() if name is None or s.name == name]

    def events(self, type: str | None = None) -> list[dict]:
        return [e for e in self.result.security["events"] if type is None or e["type"] == type]

    @property
    def decided(self) -> dict:
        outcome = self.result.classification["final"] or self.result.classification["surface"]
        return outcome["decided_by"] or {}

    @property
    def rules(self) -> list[str]:
        outcome = self.result.classification["final"] or self.result.classification["surface"]
        return [c["matched_rule"] for c in outcome["classifications"]]


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(f.relative_to(path)).encode() + f.read_bytes())
    return digest.hexdigest()



@pytest.fixture
def run_scenario(tmp_dir: Path) -> Iterator[Callable[..., Scenario]]:
    def run(
        llm: Any = None,
        *,
        pytest_script: list | None = None,
        playwright_script: list | None = None,
        http_script: list | None = None,
        agents: dict | None = None,
        requirement_text: str = "REQ-005: done is terminal",
        llm_retry: RetryPolicy | None = None,
        pytest_retry: RetryPolicy | None = None,
        max_rounds: int = 1,
    ) -> Scenario:
        workspace = create_run_workspace(tmp_dir / "artifacts", new_run_id())
        clock = FakeClock()
        fakes = {
            "pytest": FakeTool(pytest_script or [PASSED], clock=clock, duration_s=1.0),
            "playwright": FakeTool(playwright_script or [PASSED], clock=clock),
            "http_request": FakeTool(http_script or [HEALTHY], clock=clock),
        }
        registry = ToolRegistry()
        registry.register("file_write", FileWriteTool(workspace))
        registry.register("pytest", fakes["pytest"], retry=pytest_retry)
        registry.register("http_request", fakes["http_request"])
        registry.register("playwright", fakes["playwright"])
        memory = InMemorySpanExporter()
        provider, inst = new_instrumentation(clock, RunContentSink(workspace), memory, JsonFileSpanExporter(workspace, filename="trace.json"))
        kwargs = {"llm_retry": llm_retry} if llm_retry else {}
        result = run_pipeline(
            RequirementInput("REQ-005", requirement_text), llm=llm or FakeLLM(llm_script()), tools=registry, inst=inst,
            run_id=workspace.name, workspace=workspace, agents=agents, max_rounds=max_rounds, **kwargs,
        )  # fmt: skip
        provider.shutdown()
        return Scenario(result, memory, workspace, fakes)

    yield run
