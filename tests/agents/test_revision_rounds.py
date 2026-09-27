"""Revision rounds (spec v3 §4.2, §9): per-round snapshots in generated/roundN/, rounds in the result, qa.test.round
on spans. The real AutomationAgent does not revise, so a normal run has exactly one round."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from agents.base import AgentDeps
from agents.contracts import AutomationResult, GeneratedFile, RevisionRequest, TestPlan
from testing import scripts
from testing.fake_llm import FakeLLM
from tools.file_tool import FileWriteTool
from tools.registry import ToolArgumentError, ToolRegistry, ToolResult
from tools.workspace import create_run_workspace, snapshot_round
from testing.fake_tool import FakeTool

API = "generated/test_req005_api.py"


def _result(outcome: str) -> ToolResult:
    ok = outcome == "PASS"
    return ToolResult(ok=ok, exit_code=0 if ok else 1, stdout=f"1 {'passed' if ok else 'failed'}",
                      data={"results": [{"node_id": f"{API}::test_rule", "outcome": outcome, "message": "" if ok else "assert 200 == 409"}]})  # fmt: skip


def _tools(outcomes: list[str]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("file_write", FakeTool([ToolResult(ok=True, command="file_write")] * 10))
    registry.register("pytest", FakeTool([_result(o) for o in outcomes]))
    registry.register("http_request", FakeTool([ToolResult(ok=True, data={"method": "GET", "route": "/health", "status_code": 200})] * 10))
    registry.register("playwright", FakeTool([ToolResult(ok=True)]))
    return registry


class Reviser:
    """Minimal revising automation agent: round N writes 'v{N}' of the same file."""

    name = "automation"
    revises = True

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps
        self.requests: list[Any] = []

    def run(self, request: TestPlan | RevisionRequest) -> AutomationResult:
        self.requests.append(request)
        n = request.round if isinstance(request, RevisionRequest) else 1
        content = f"def test_rule():\n    assert 'v{n}'\n"
        self.deps.tools.call("file_write", path=API, content=content)
        return AutomationResult("REQ-005", (GeneratedFile(API, content, "api"),))


def _llm() -> FakeLLM:
    return FakeLLM(scripts.llm_script("REQ-005")[:2])


def test_real_automation_agent_runs_one_round(harness):
    result = harness.run(scenario="defect", sut_bugs=("B02",), max_rounds=3)

    assert [r["round"] for r in result.rounds] == [1]
    assert result.rounds[0]["results"][0]["outcome"] == "FAIL"
    assert result.rounds[0]["files"][0]["snapshot"] is None  # no workspace: hashes only


def test_reviser_gets_revision_requests_until_tests_pass(harness, tmp_dir):
    workspace = create_run_workspace(tmp_dir, "RUN-20260927-120000-ABCD")
    made: list[Reviser] = []

    def factory(deps: AgentDeps) -> Reviser:
        made.append(Reviser(deps))
        return made[0]

    result = harness.run(llm=_llm(), tools=_tools(["FAIL", "FAIL", "PASS", "PASS"]), agents={"automation": factory},
                                  workspace=workspace, max_rounds=5)  # fmt: skip

    assert [r["round"] for r in result.rounds] == [1, 2, 3]
    assert [r["results"][0]["outcome"] for r in result.rounds] == ["FAIL", "FAIL", "PASS"]
    requests = made[0].requests
    assert isinstance(requests[0], TestPlan)
    assert [(r.round, r.qa.executions[0].ok) for r in requests[1:]] == [(2, False), (3, False)]
    assert requests[2].previous.files[0].content == "def test_rule():\n    assert 'v2'\n"
    for n in (1, 2, 3):
        snap = workspace / "generated" / f"round{n}" / "test_req005_api.py"
        assert snap.read_text(encoding="utf-8") == f"def test_rule():\n    assert 'v{n}'\n"
        assert result.rounds[n - 1]["files"][0]["snapshot"] == f"generated/round{n}/test_req005_api.py"

    automation_spans = harness.named("agent.automation")
    assert [s.attributes["qa.test.round"] for s in automation_spans] == [1, 2, 3]
    assert [s.attributes["qa.test.round"] for s in harness.named("tool.pytest")] == [1, 2, 3]
    assert "qa.test.round" not in harness.one("agent.report").attributes


def test_max_rounds_caps_revisions(harness):
    result = harness.run(llm=_llm(), tools=_tools(["FAIL"] * 5), agents={"automation": Reviser}, max_rounds=2)
    assert [r["round"] for r in result.rounds] == [1, 2]


def test_passing_first_round_is_not_revised(harness):
    result = harness.run(llm=_llm(), tools=_tools(["PASS"]), agents={"automation": Reviser}, max_rounds=3)
    assert [r["round"] for r in result.rounds] == [1]


def test_max_rounds_must_be_positive(harness):
    with pytest.raises(ValueError):
        harness.run(llm=_llm(), tools=_tools(["PASS"]), max_rounds=0)


# --------------------------------------------------------------------------- snapshots


def test_snapshot_is_read_only_and_never_overwritten(tmp_dir: Path):
    saved = snapshot_round(tmp_dir, 1, [("generated/test_a.py", "x = 1\n")])
    target = tmp_dir / "generated" / "round1" / "test_a.py"
    digest = hashlib.sha256(b"x = 1\n").hexdigest()
    assert saved == [{"path": "generated/test_a.py", "snapshot": "generated/round1/test_a.py", "sha256": digest}]
    assert not os.stat(target).st_mode & stat.S_IWRITE
    with pytest.raises(PermissionError):
        target.write_text("tampered", encoding="utf-8")
    with pytest.raises(FileExistsError):
        snapshot_round(tmp_dir, 1, [("generated/test_a.py", "x = 2\n")])


def test_file_write_refuses_round_snapshots(tmp_dir: Path):
    (tmp_dir / "generated").mkdir()
    tool = FileWriteTool(tmp_dir)
    with pytest.raises(ToolArgumentError, match="round snapshots"):
        tool(path="generated/round1/test_a.py", content="x = 1\n")
    tool(path="generated/rounds_helper/test_a.py", content="x = 1\n")  # only roundN/ is reserved
