"""Permission gate (spec v3 §8.1, §7): every cell of the permission table, and path handling.

Paths are judged after resolve() + normcase(); writing into the run's own generated/ is decided before
the evidence check. A fake repo layout in a temp dir stands in for the real one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from permissions.gate import PERMISSIONS, PermissionGate
from security.events import SecurityRecorder
from tools.registry import PermissionDeniedError, UnknownToolError

TOOLS = ("file_write", "pytest", "http_request", "playwright")
AGENTS = ("requirement", "test_design", "automation", "qa", "report")
WINDOWS = os.name == "nt"


@pytest.fixture
def repo(tmp_dir: Path) -> Path:
    for d in ("sut", "docs", "benchmark/reference_tests", "benchmark/results", "traces", "artifacts/RUN-20260926-000000-AAAA/generated",
              "artifacts/RUN-20260926-000000-BBBB/generated"):  # fmt: skip
        (tmp_dir / d).mkdir(parents=True)
    return tmp_dir


@pytest.fixture
def gate(repo: Path) -> PermissionGate:
    workspace = repo / "artifacts" / "RUN-20260926-000000-AAAA"
    return PermissionGate(SecurityRecorder("RUN-20260926-000000-AAAA"), registered=lambda: TOOLS, workspace=workspace, repo_root=repo)


def _args(tool: str) -> dict:
    return {
        "file_write": {"path": "generated/test_x.py", "content": "def test_x():\n    assert True\n"},
        "pytest": {"paths": ["generated/test_x.py"]},
        "playwright": {"paths": ["generated/test_x.py"]},
        "http_request": {"method": "GET", "route": "/health"},
    }[tool]


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("tool", TOOLS)
def test_permission_table_cell(gate, agent, tool):
    """§8.1: allowed cells pass the gate; every other cell is refused with PERMISSION_DENIED, not executed."""
    allowed = tool in PERMISSIONS[agent]
    if allowed:
        gate.check(agent, tool, _args(tool))
        assert gate.recorder.events == []
    else:
        with pytest.raises(PermissionDeniedError):
            gate.check(agent, tool, _args(tool))
        (event,) = gate.recorder.events
        assert (event.type, event.agent, event.action, event.executed) == ("PERMISSION_DENIED", agent, tool, False)


def test_permission_table_matches_spec():
    assert PERMISSIONS == {
        "requirement": set(), "test_design": set(), "qa": {"pytest", "http_request", "playwright"}, "report": set(),
        "automation": {"file_write", "pytest", "http_request", "playwright"},
    }  # fmt: skip


def test_unregistered_tool_is_invalid_tool_call(gate):
    with pytest.raises(UnknownToolError):
        gate.check("automation", "shell", {"cmd": "rm -rf /"})
    (event,) = gate.recorder.events
    assert (event.type, event.executed) == ("INVALID_TOOL_CALL", False)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("generated/test_ok.py", "OWN_GENERATED"),
        ("generated/sub/test_ok.py", "OWN_GENERATED"),
        ("sut/app.py", "PROTECTED"),
        ("docs/spec.md", "PROTECTED"),
        ("benchmark/reference_tests/test_b01_x.py", "PROTECTED"),
        ("benchmark/bugs.yaml", "EVIDENCE"),
        ("traces/x.json", "EVIDENCE"),
        ("artifacts/RUN-20260926-000000-BBBB/generated/test_x.py", "EVIDENCE"),
        ("notes/test_x.py", "EVIDENCE"),  # lands in this run's own directory, outside generated/
        # ../ traversal out of the run workspace
        ("generated/../../RUN-20260926-000000-BBBB/meta.json", "EVIDENCE"),
        ("../RUN-20260926-000000-BBBB/generated/test_x.py", "EVIDENCE"),
        ("../../sut/app.py", "PROTECTED"),  # workspace = <repo>/artifacts/RUN-A
        ("../../../sut/app.py", "OUTSIDE"),  # one level too far: outside the repo
        ("generated/../../../docs/spec.md", "PROTECTED"),
        ("generated/../meta.json", "EVIDENCE"),  # own run directory, but not generated/: evidence
    ],
)
def test_path_classification(gate, path, expected):
    assert gate.classify_path(path) == expected


def test_absolute_paths(gate, repo):
    workspace = repo / "artifacts" / "RUN-20260926-000000-AAAA"
    assert gate.classify_path(str(workspace / "generated" / "test_x.py")) == "OWN_GENERATED"
    assert gate.classify_path(str(repo / "sut" / "app.py")) == "PROTECTED"
    assert gate.classify_path(str(repo / "artifacts" / "RUN-20260926-000000-BBBB" / "trace.json")) == "EVIDENCE"
    assert gate.classify_path(str(repo.parent / "elsewhere.py")) == "OUTSIDE"


@pytest.mark.skipif(not WINDOWS, reason="case-insensitive paths and backslash separators are Windows semantics")
@pytest.mark.parametrize(
    "path, expected",
    [
        ("GENERATED/Test_Ok.py", "OWN_GENERATED"),
        ("generated\\test_ok.py", "OWN_GENERATED"),
        ("SUT/APP.PY", "PROTECTED"),
        ("Sut\\App.py", "PROTECTED"),
        ("..\\..\\SUT\\app.py", "PROTECTED"),
        ("DOCS\\Spec.md", "PROTECTED"),
        ("Benchmark\\Reference_Tests\\t.py", "PROTECTED"),
        ("..\\RUN-20260926-000000-bbbb\\meta.json", "EVIDENCE"),
        ("generated\\..\\..\\RUN-20260926-000000-BBBB\\trace.json", "EVIDENCE"),
    ],
)
def test_windows_case_and_backslash(gate, path, expected):
    assert gate.classify_path(path) == expected


@pytest.mark.skipif(not WINDOWS, reason="Windows absolute path forms")
def test_windows_absolute_path_with_other_case_and_separators(gate, repo):
    mixed = str(repo / "sut" / "app.py").upper().replace("\\", "/")
    assert gate.classify_path(mixed) == "PROTECTED"


def test_protected_write_records_goal_drift_and_refuses(gate):
    with pytest.raises(PermissionDeniedError):
        gate.check("automation", "file_write", {"path": "sut/app.py", "content": "x = 1\n"})
    types = [e.type for e in gate.recorder.events]
    assert types == ["GOAL_DRIFT", "PROTECTED_PATH_WRITE"]
    assert all(e.executed is False for e in gate.recorder.events)


def test_evidence_write_is_tamper_attempt(gate):
    with pytest.raises(PermissionDeniedError):
        gate.check("automation", "file_write", {"path": "../RUN-20260926-000000-BBBB/trace.json", "content": "{}"})
    (event,) = gate.recorder.events
    assert (event.type, event.executed) == ("EVIDENCE_TAMPER_ATTEMPT", False)


def test_own_generated_is_checked_before_evidence(gate):
    """The run's generated/ lives under artifacts/ (an evidence root); it must still be writable."""
    gate.check("automation", "file_write", {"path": "generated/test_ok.py", "content": "def test_a():\n    pass\n"})
    assert gate.recorder.events == []


@pytest.mark.parametrize("route", ["http://evil.test/x", "https://127.0.0.1:9/api", "//evil.test/x", "api/tasks"])
def test_http_request_only_to_sut_paths(gate, route):
    with pytest.raises(PermissionDeniedError):
        gate.check("qa", "http_request", {"method": "GET", "route": route})
    assert gate.recorder.events[0].type == "PERMISSION_DENIED"


def test_breach_only_when_something_executed(gate):
    with pytest.raises(PermissionDeniedError):
        gate.check("qa", "file_write", _args("file_write"))
    assert gate.recorder.breach is False


@pytest.mark.skipif(not WINDOWS, reason="case-insensitive paths are Windows semantics")
def test_case_is_normalised_even_for_directories_that_do_not_exist_yet(tmp_dir):
    """resolve() only canonicalises the case of existing directories; normcase covers the rest
    (e.g. a run whose generated/ is not created yet, or a repo without traces/)."""
    repo = tmp_dir / "repo"
    (repo / "artifacts").mkdir(parents=True)
    workspace = repo / "artifacts" / "RUN-20260926-000000-CCCC"  # not created on disk
    gate = PermissionGate(SecurityRecorder(), registered=lambda: TOOLS, workspace=workspace, repo_root=repo)
    assert gate.classify_path("GENERATED/Test_New.py") == "OWN_GENERATED"
    assert gate.classify_path("TRACES/x.json") == "EVIDENCE"
    assert gate.classify_path("SUT/app.py") == "PROTECTED"
