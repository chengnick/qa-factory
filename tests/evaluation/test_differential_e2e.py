"""Cross-validation end to end: FakeLLM writes pre-written tests, real SUTs run them (offline).

The test file below produces each row of spec v3 §6.2 against B02 (dev set) vs a clean SUT.
"""

from __future__ import annotations

import contextlib
import json
import urllib.request
from pathlib import Path

import pytest

from evaluation.run import execute_run
from sut.launcher import free_port, running_sut
from testing.fake_llm import FakeLLM

SIX_CASES = '''
import pytest


def _done_task(client, pid):
    tid = client.post(f"/api/projects/{pid}/tasks", json={"title": "t"}).json()["id"]
    for to in ("in_progress", "done"):
        assert client.post(f"/api/tasks/{tid}/transition", json={"to": to}).status_code == 200
    return tid


def test_r11_detects_reopen(as_user, new_project):
    alice = as_user("alice")
    tid = _done_task(alice, new_project())
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_r12_always_wrong():
    assert 1 == 2


def test_r13_expects_the_bug(as_user, new_project):
    alice = as_user("alice")
    tid = _done_task(alice, new_project())
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text


def test_pass_pass_create(as_user, new_project):
    r = as_user("alice").post(f"/api/projects/{new_project()}/tasks", json={"title": "ok"})
    assert r.status_code == 201, r.text


def test_r10_fixture_misuse(as_user):
    as_user.post("/api/projects", json={"name": "x"})


def test_seed_users_are_fixed(as_user, user_ids):
    # Fresh SUT: seeded users only, alice has no projects yet in this build (first test to look).
    assert user_ids == {"alice": 1, "bob": 2, "carol": 3, "dave": 4}
'''

EXPECTED = {
    "generated/test_req005_api.py::test_r11_detects_reopen": ("FAIL", "PASS", "DETECTED", "R11"),
    "generated/test_req005_api.py::test_r12_always_wrong": ("FAIL", "FAIL", "BROKEN", "R12"),
    "generated/test_req005_api.py::test_r13_expects_the_bug": ("PASS", "FAIL", "BROKEN", "R13"),
    "generated/test_req005_api.py::test_pass_pass_create": ("PASS", "PASS", "NOT_DETECTED", None),
    "generated/test_req005_api.py::test_r10_fixture_misuse": ("ERROR", "ERROR", "BROKEN", "R10"),
    "generated/test_req005_api.py::test_seed_users_are_fixed": ("PASS", "PASS", "NOT_DETECTED", None),
}


def scripted_llm(content: str = SIX_CASES) -> FakeLLM:
    requirement = {"summary": "done is terminal", "acceptance_criteria": ["done -> in_progress is 409"]}
    plan = {"cases": [{"id": "TC-1", "title": "x", "surface": "api", "steps": ["..."], "expected": "409"}]}
    files = {"files": [{"path": "generated/test_req005_api.py", "surface": "api", "content": content}]}
    return FakeLLM([json.dumps(requirement), json.dumps(plan), json.dumps(files)])


def _run(tmp_dir: Path, bugs, sut_factory=running_sut):
    return execute_run(
        requirement_id="REQ-005", sut_bugs=bugs, llm=scripted_llm(), llm_kind="fake", model="fake-model",
        artifacts_dir=tmp_dir, sut_factory=sut_factory,
    )  # fmt: skip


@pytest.fixture(scope="module")
def b02_run(tmp_path_factory_safe):
    return _run(tmp_path_factory_safe, ["B02"])


@pytest.fixture(scope="module")
def tmp_path_factory_safe():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="qa-diff-") as d:
        yield Path(d)


def test_each_spec_row_is_decided_per_node_id(b02_run):
    workspace, meta = b02_run
    diff = json.loads((workspace / "differential.json").read_text(encoding="utf-8"))

    got = {d["node_id"]: (d["bug_outcome"], d["clean_outcome"], d["decision"], d["rule"]) for d in diff["decisions"]}
    assert got == EXPECTED
    assert diff["status"] == "COMPLETE" and diff["verdict"] == "DEFECT_FOUND"
    assert diff["counts"] == {"detected": 1, "missed": 2, "broken": 3, "passed": 0, "tests": 6}
    assert diff["test_health"] == {"healthy": 3, "total": 6}
    assert meta["verdict"] == "DEFECT_FOUND" and meta["differential"]["status"] == "COMPLETE"


def test_surface_verdict_comes_from_the_pipeline_run(b02_run):
    _, meta = b02_run
    # The pipeline's own QA run saw assertion failures (R11U, unverified SUT) and an AttributeError (R10).
    # Phase 3 aggregation puts DEFECT_FOUND before TEST_BROKEN (spec v3 §6.3), so the surface is DEFECT_FOUND;
    # only cross-validation shows which failure actually depends on the bug.
    assert meta["surface_verdict"] == "DEFECT_FOUND"


def test_builds_are_symmetric(b02_run):
    workspace, _ = b02_run
    diff = json.loads((workspace / "differential.json").read_text(encoding="utf-8"))
    bug, clean = diff["builds"]
    assert (bug["build"], bug["sut_bugs"]) == ("bug", ["B02"]) and (clean["build"], clean["sut_bugs"]) == ("clean", [])
    strip = lambda runs: [(r["tool"], r["paths"], r["attempts"]) for r in runs]  # noqa: E731
    assert strip(bug["runs"]) == strip(clean["runs"]) == [("pytest", ["generated/test_req005_api.py"], 1)]
    assert (workspace / "pytest" / "bug_build.log").is_file() and (workspace / "pytest" / "clean_build.log").is_file()


def test_tests_are_not_modified_between_builds(b02_run):
    workspace, _ = b02_run
    diff = json.loads((workspace / "differential.json").read_text(encoding="utf-8"))
    import hashlib

    current = hashlib.sha256((workspace / "generated" / "test_req005_api.py").read_bytes()).hexdigest()
    assert diff["file_hashes"] == {"generated/test_req005_api.py": current}


def test_trace_contains_differential_under_the_same_run(b02_run):
    workspace, meta = b02_run
    trace = json.loads((workspace / "trace.json").read_text(encoding="utf-8"))
    by_id = {s["span_id"]: s for s in trace["spans"]}
    (diff_span,) = [s for s in trace["spans"] if s["name"] == "evaluation.differential"]
    assert by_id[diff_span["parent_span_id"]]["name"] == "qa.run"
    builds = [s for s in trace["spans"] if s["name"] == "evaluation.build"]
    assert [b["attributes"]["qa.eval.build"] for b in builds] == ["bug", "clean"]
    assert all(b["parent_span_id"] == diff_span["span_id"] for b in builds)
    test_ids = {e["attributes"]["qa.test.id"] for e in diff_span["events"] if e["name"] == "qa.test"}
    assert test_ids == set(EXPECTED)
    root = next(s for s in trace["spans"] if s["parent_span_id"] is None)
    assert root["attributes"]["qa.verdict"] == "DEFECT_FOUND" and root["attributes"]["qa.verdict.surface"] == "DEFECT_FOUND"
    assert root["attributes"]["qa.failure.rule"] == "R11"
    assert trace["trace_id"] == meta["trace_id"]


def test_fresh_suts_start_from_identical_seed():
    snapshots = []
    for bugs in ([], ["B02"]):
        with running_sut(bugs) as url:
            req = urllib.request.Request(f"{url}/api/projects", headers={"X-User": "alice"})
            with urllib.request.urlopen(f"{url}/api/users") as users, urllib.request.urlopen(req) as projects:
                snapshots.append((json.load(users), json.load(projects)))
    assert snapshots[0] == snapshots[1] == ([{"id": i, "username": u} for i, u in enumerate(["alice", "bob", "carol", "dave"], 1)], [])


def test_unhealthy_build_makes_cross_validation_env_blocked(tmp_dir):
    """Clean-build SUT down: no test is judged (no R12/R13) and nothing counts toward test health."""
    calls = []

    @contextlib.contextmanager
    def flaky_factory(bugs):
        calls.append(list(bugs))
        if len(calls) == 3:  # 1 = pipeline SUT, 2 = bug build, 3 = clean build -> dead
            yield f"http://127.0.0.1:{free_port()}"
        else:
            with running_sut(bugs) as url:
                yield url

    workspace, meta = _run(tmp_dir, ["B02"], sut_factory=flaky_factory)

    diff = json.loads((workspace / "differential.json").read_text(encoding="utf-8"))
    assert calls == [["B02"], ["B02"], []]
    assert diff["status"] == "ENV_BLOCKED" and diff["decisions"] == [] and diff["test_health"] is None
    assert "clean build" in diff["reason"]
    assert meta["verdict"] == "ENV_BLOCKED"
    trace = json.loads((workspace / "trace.json").read_text(encoding="utf-8"))
    clean_build = [s for s in trace["spans"] if s["name"] == "evaluation.build"][1]
    assert clean_build["attributes"]["qa.failure.layer"] == "ENV"
    assert clean_build["attributes"]["qa.failure.symptom"] == "CONNECTION"
    assert clean_build["attributes"]["qa.failure.rule"] == "R1"
