"""Each policy field is really read from the file: changing it changes behaviour (spec v3.1 §8.5.5).

Every case asserts the default behaviour first, then the behaviour under a modified temp policy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from permissions.gate import PermissionGate
from permissions.policy import load_policy
from security.events import SecurityRecorder
from tests.policy.support import modified
from tools.code_policy import check_source
from tools.registry import PermissionDeniedError

TOOLS = ("file_write", "pytest", "http_request", "playwright")
SUT = "http://127.0.0.1:61234"


@pytest.fixture
def repo(tmp_dir: Path) -> Path:
    for d in ("sut", "docs", "config", "benchmark/reference_tests", "traces", "artifacts/RUN-20260927-000000-AAAA/generated",
              "artifacts/RUN-20260927-000000-AAAA/other"):  # fmt: skip
        (tmp_dir / d).mkdir(parents=True)
    return tmp_dir


def _gate(repo: Path, policy=None) -> PermissionGate:
    workspace = repo / "artifacts" / "RUN-20260927-000000-AAAA"
    return PermissionGate(SecurityRecorder(), registered=lambda: TOOLS, workspace=workspace, repo_root=repo, sut_url=SUT, policy=policy)


def _allowed(gate: PermissionGate, agent: str, tool: str, args: dict) -> bool:
    try:
        gate.check(agent, tool, args)
    except PermissionDeniedError:
        return False
    return True


WRITE = {"path": "generated/test_a.py", "content": "def test_a():\n    pass\n"}
RUN = {"paths": ["generated/test_a.py"]}
HTTP = {"method": "GET", "route": "/health"}


# ---- agents.<agent>.tools: one case per tool --------------------------------------------------------------


@pytest.mark.parametrize(
    "agent, tool, args, grant",
    [
        ("qa", "file_write", WRITE, True),  # the spec's example: give QA file_write
        ("automation", "pytest", RUN, False),
        ("qa", "http_request", HTTP, False),
        ("qa", "playwright", RUN, False),
        ("report", "pytest", RUN, True),
    ],
)
def test_tool_permission_follows_the_file(repo, tmp_dir, agent, tool, args, grant):
    before = _allowed(_gate(repo), agent, tool, args)

    def change(raw):
        tools = raw["agents"][agent]["tools"]
        if grant:
            tools[tool] = {"path_prefix": "artifacts/{run_id}/generated/"} if tool == "file_write" else {}
        else:
            del tools[tool]

    after = _allowed(_gate(repo, modified(tmp_dir, change)), agent, tool, args)
    assert (before, after) == (not grant, grant)


# ---- conditions --------------------------------------------------------------------------------------------


def test_path_prefix(repo, tmp_dir):
    def change(raw):
        raw["agents"]["automation"]["tools"]["file_write"]["path_prefix"] = "artifacts/{run_id}/other/"

    default, changed = _gate(repo), _gate(repo, modified(tmp_dir, change))
    assert default.classify_path("generated/test_a.py") == "OWN_GENERATED" and default.classify_path("other/test_a.py") == "EVIDENCE"
    assert changed.classify_path("generated/test_a.py") == "EVIDENCE" and changed.classify_path("other/test_a.py") == "OWN_GENERATED"


def test_agent_url_allowlist(repo, tmp_dir):
    def change(raw):
        raw["agents"]["qa"]["tools"]["http_request"]["url_allowlist"] = ["{sut_base_url}/api/"]

    assert _allowed(_gate(repo), "qa", "http_request", HTTP)
    changed = _gate(repo, modified(tmp_dir, change))
    assert not _allowed(changed, "qa", "http_request", HTTP)
    assert _allowed(changed, "qa", "http_request", {"method": "GET", "route": "/api/users"})


# Absolute repo paths isolate the protected/evidence lists: a relative path also resolves inside the
# run's own directory (under artifacts/, which is evidence), so it would be EVIDENCE either way.


def test_protected_paths(repo, tmp_dir):
    config, docs = str(repo / "config" / "agent_policy.yaml"), str(repo / "docs" / "spec.md")
    policy = modified(tmp_dir, lambda raw: raw["paths"]["protected"].append("config/"))
    assert _gate(repo).classify_path(config) == "OUTSIDE"
    assert _gate(repo, policy).classify_path(config) == "PROTECTED"
    policy = modified(tmp_dir, lambda raw: raw["paths"]["protected"].remove("docs/"))
    assert _gate(repo).classify_path(docs) == "PROTECTED"
    assert _gate(repo, policy).classify_path(docs) == "OUTSIDE"


def test_evidence_paths(repo, tmp_dir):
    traces, config = str(repo / "traces" / "x.json"), str(repo / "config" / "x.yaml")
    policy = modified(tmp_dir, lambda raw: raw["paths"]["evidence"].remove("traces/"))
    assert _gate(repo).classify_path(traces) == "EVIDENCE"
    assert _gate(repo, policy).classify_path(traces) == "OUTSIDE"
    policy = modified(tmp_dir, lambda raw: raw["paths"]["evidence"].append("config/"))
    assert _gate(repo).classify_path(config) == "OUTSIDE"
    assert _gate(repo, policy).classify_path(config) == "EVIDENCE"


def test_allowed_imports(tmp_dir):
    policy = modified(tmp_dir, lambda raw: raw["generated_code"]["allowed_imports"].append("json"))
    assert check_source("import json\n", sut_url=SUT)
    assert check_source("import json\n", sut_url=SUT, policy=policy) == []


def test_banned_names(tmp_dir):
    removed = modified(tmp_dir, lambda raw: raw["generated_code"]["banned_names"].remove("getattr"))
    added = modified(tmp_dir, lambda raw: raw["generated_code"]["banned_names"].append("print"))
    assert check_source("getattr(1, 'x')\n", sut_url=SUT) and check_source("getattr(1, 'x')\n", sut_url=SUT, policy=removed) == []
    assert check_source("print(1)\n", sut_url=SUT) == [] and check_source("print(1)\n", sut_url=SUT, policy=added)


def test_banned_attributes(tmp_dir):
    policy = modified(tmp_dir, lambda raw: raw["generated_code"]["banned_attributes"].remove("__class__"))
    assert check_source("x = ().__class__\n", sut_url=SUT)
    assert check_source("x = ().__class__\n", sut_url=SUT, policy=policy) == []


def test_generated_code_url_allowlist(tmp_dir):
    source = "u = 'https://docs.example.test/page'\n"
    policy = modified(tmp_dir, lambda raw: raw["generated_code"]["url_allowlist"].append("https://docs.example.test/"))
    assert check_source(source, sut_url=SUT)
    assert check_source(source, sut_url=SUT, policy=policy) == []


def test_runner_check_uses_the_runs_policy(repo, tmp_dir):
    """The gate hands its policy to the generated-code check (pytest / playwright)."""
    (repo / "artifacts" / "RUN-20260927-000000-AAAA" / "generated" / "test_a.py").write_text("import json\n", encoding="utf-8")
    policy = modified(tmp_dir, lambda raw: raw["generated_code"]["allowed_imports"].append("json"))
    assert not _allowed(_gate(repo), "qa", "pytest", RUN)
    assert _allowed(_gate(repo, policy), "qa", "pytest", RUN)


def test_default_policy_loads(tmp_dir):
    assert load_policy().permissions()["qa"] == frozenset({"pytest", "http_request", "playwright"})
