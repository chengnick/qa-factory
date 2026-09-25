"""End-to-end with real tools and a real SUT, but a scripted LLM (offline, deterministic).

Proves the plumbing Phase 2 relies on: file_write -> generated/ -> pytest subprocess with the
owner fixtures -> SUT over HTTP -> Playwright -> verdict, independent of any real model.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agents.contracts import RequirementInput
from pipeline import run_pipeline
from sut.launcher import free_port, running_sut
from testing.fake_llm import FakeLLM
from tools.factory import real_tools

REPO = Path(__file__).resolve().parents[2]

API_TEST = '''
def test_done_task_cannot_reopen(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "ship"}).json()["id"]
    for to in ("in_progress", "done"):
        r = alice.post(f"/api/tasks/{tid}/transition", json={"to": to})
        assert r.status_code == 200, r.text
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
'''

UI_TEST = '''
from playwright.sync_api import expect


def test_new_task_shows_todo(base_url, as_user, new_project, page):
    pid = new_project()
    as_user("alice").post(f"/api/projects/{pid}/tasks", json={"title": "visible"})
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    expect(page.get_by_test_id("task-status")).to_have_text(["todo"])
'''


def _script(files: list[dict]) -> FakeLLM:
    requirement = {"summary": "done is terminal", "acceptance_criteria": ["done -> in_progress is 409"]}
    plan = {"cases": [{"id": "TC-1", "title": "reopen done", "surface": "api", "steps": ["..."], "expected": "409"}]}
    return FakeLLM([json.dumps(requirement), json.dumps(plan), json.dumps({"files": files})])


API_FILE = {"path": "generated/test_req005_api.py", "surface": "api", "content": API_TEST}
UI_FILE = {"path": "generated/test_req005_ui.py", "surface": "ui", "content": UI_TEST}


@pytest.fixture
def root(tmp_dir: Path) -> Path:
    (tmp_dir / "generated").mkdir()
    shutil.copy(REPO / "generated" / "conftest.py", tmp_dir / "generated" / "conftest.py")
    return tmp_dir


def _run(harness, root: Path, url: str, files: list[dict], bugs=()):
    return run_pipeline(
        RequirementInput("REQ-005", "text"),
        llm=_script(files),
        tools=real_tools(root, url),
        inst=harness.inst,
        sut_bugs=bugs,
    )


def test_clean_sut_passes_api_and_ui(harness, root):
    with running_sut([]) as url:
        result = _run(harness, root, url, [API_FILE, UI_FILE])

    assert result.verdict == "PASS", result.report.summary
    assert (root / "generated" / "test_req005_api.py").is_file()
    assert harness.one("tool.pytest").attributes["qa.tool.exit_code"] == 0
    assert harness.one("tool.playwright").attributes["qa.tool.exit_code"] == 0
    assert harness.one("tool.http_request").attributes["qa.http.status_code"] == 200


def test_seeded_bug_is_found(harness, root):
    with running_sut(["B02"]) as url:
        result = _run(harness, root, url, [API_FILE], bugs=("B02",))

    assert result.verdict == "DEFECT_FOUND", result.report.summary
    tail = next(e for e in harness.one("tool.pytest").events if e.name == "stdout.tail")
    assert "409" in tail.attributes["text"]


def test_broken_generated_test_is_test_broken(harness, root):
    broken = {**API_FILE, "content": "def test_x(:\n    pass\n"}
    with running_sut([]) as url:
        result = _run(harness, root, url, [broken])

    assert result.verdict == "TEST_BROKEN", result.report.summary


def test_dead_sut_is_env_blocked(harness, root):
    dead_url = f"http://127.0.0.1:{free_port()}"

    result = _run(harness, root, dead_url, [API_FILE])

    assert result.verdict == "ENV_BLOCKED", result.report.summary
    assert harness.one("tool.http_request").attributes["qa.failure.symptom"] == "CONNECTION"
