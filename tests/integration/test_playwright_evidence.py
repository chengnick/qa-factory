"""Playwright evidence (spec v3 §4.2, Phase 4): a failing UI test leaves trace.zip, screenshot.png and console.log
in playwright/{call}/{test}/, a passing one leaves nothing, and the tool span names the folders in qa.artifact.path."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from agents.contracts import RequirementInput
from pipeline import run_pipeline
from sut.launcher import running_sut
from testing.fake_llm import FakeLLM
from tools.factory import real_tools

REPO = Path(__file__).resolve().parents[2]

UI_TESTS = '''
from playwright.sync_api import expect


def _board(base_url, as_user, new_project, page):
    pid = new_project()
    as_user("alice").post(f"/api/projects/{pid}/tasks", json={"title": "visible"})
    page.goto(f"{base_url}/?user=alice&project={pid}")
    page.evaluate("console.log('evidence-marker')")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")


def test_board_shows_todo(base_url, as_user, new_project, page):
    _board(base_url, as_user, new_project, page)
    expect(page.get_by_test_id("task-status")).to_have_text(["todo"])


def test_board_expects_wrong_status(base_url, as_user, new_project, page):
    _board(base_url, as_user, new_project, page)
    expect(page.get_by_test_id("task-status")).to_have_text(["done"], timeout=1000)
'''


@pytest.fixture
def root(tmp_dir: Path) -> Path:
    (tmp_dir / "generated").mkdir()
    shutil.copy(REPO / "generated" / "conftest.py", tmp_dir / "generated" / "conftest.py")
    return tmp_dir


def _llm() -> FakeLLM:
    requirement = {"summary": "board", "acceptance_criteria": ["new tasks show todo"]}
    plan = {"cases": [{"id": "TC-1", "title": "board", "surface": "ui", "steps": ["open"], "expected": "todo"}]}
    files = {"files": [{"path": "generated/test_req005_ui.py", "surface": "ui", "content": UI_TESTS}]}
    return FakeLLM([json.dumps(requirement), json.dumps(plan), json.dumps(files)])


def test_failed_ui_test_keeps_trace_screenshot_and_console(harness, root):
    with running_sut([]) as url:
        run_pipeline(RequirementInput("REQ-005", "text"), llm=_llm(), tools=real_tools(root, url), inst=harness.inst)

    calls = [d for d in (root / "playwright").iterdir() if d.is_dir()]
    assert len(calls) == 1, calls
    kept = sorted(d.name for d in calls[0].iterdir())
    assert kept == ["test_board_expects_wrong_status"], "only the failing test keeps evidence"

    folder = calls[0] / "test_board_expects_wrong_status"
    assert sorted(p.name for p in folder.iterdir()) == ["console.log", "screenshot.png", "trace.zip"]
    assert (folder / "screenshot.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert zipfile.is_zipfile(folder / "trace.zip")
    assert "[log] evidence-marker" in (folder / "console.log").read_text(encoding="utf-8")

    span = harness.one("tool.playwright")
    paths = list(span.attributes["qa.artifact.path"])
    assert paths[0].startswith("reports/junit-") and paths[0].endswith(".xml")
    assert paths[1:] == [folder.relative_to(root).as_posix()]
    assert all((root / p).exists() for p in paths)


def test_api_runner_leaves_no_playwright_folder(harness, root):
    api = "def test_ok(base_url):\n    assert base_url\n\ndef test_fail():\n    assert 1 == 2\n"
    requirement = {"summary": "s", "acceptance_criteria": ["a"]}
    plan = {"cases": [{"id": "TC-1", "title": "t", "surface": "api", "steps": ["s"], "expected": "e"}]}
    files = {"files": [{"path": "generated/test_req005_api.py", "surface": "api", "content": api}]}
    llm = FakeLLM([json.dumps(requirement), json.dumps(plan), json.dumps(files)])
    with running_sut([]) as url:
        run_pipeline(RequirementInput("REQ-005", "text"), llm=llm, tools=real_tools(root, url), inst=harness.inst)

    assert not (root / "playwright").exists()
    assert list(harness.one("tool.pytest").attributes["qa.artifact.path"])[0].startswith("reports/junit-")
