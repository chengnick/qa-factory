"""Static checks of the CI workflows (spec v3.1 §15.5): no secrets, pinned actions, the agreed job shape."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))
PINNED = re.compile(r"^\s*-?\s*uses:\s*[\w.\-]+/[\w.\-/]+@[0-9a-f]{40}\s+#\s*v\d+\.\d+\.\d+\s*$")


def _load(path: Path) -> dict:
    # PyYAML reads the key `on` as boolean True (YAML 1.1); normalise it.
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in data:
        data["on"] = data.pop(True)
    return data


def test_there_is_a_workflow():
    assert [p.name for p in WORKFLOWS] == ["ci.yml"]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_secret_is_referenced(path):
    text = path.read_text(encoding="utf-8")
    assert "secrets." not in text and "secrets[" not in text, f"{path.name} references a secret (spec v3.1 D20)"
    assert "GEMINI_API_KEY" not in text


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_actions_are_pinned_to_a_commit_sha_with_version_comment(path):
    uses = [line for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"^\s*-?\s*uses:", line)]
    assert uses
    for line in uses:
        assert PINNED.match(line), f"not pinned to a 40-hex SHA with '# vX.Y.Z': {line.strip()}"


def test_ci_job_shape():
    ci = _load(REPO / ".github" / "workflows" / "ci.yml")
    assert set(ci["on"]) == {"push", "pull_request"}
    assert ci["concurrency"]["cancel-in-progress"] is True
    test = ci["jobs"]["test"]
    assert test["strategy"]["fail-fast"] is False
    assert test["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    assert test["timeout-minutes"] == 20
    steps = {s.get("name", s.get("uses", "")): s for s in test["steps"]}
    setup = next(s for s in test["steps"] if "setup-python" in s.get("uses", ""))
    assert setup["with"] == {"python-version-file": ".python-version"}  # no second copy of the version
    assert steps["Install dependencies (lockfile)"]["run"] == "python -m pip install -r requirements.lock"
    # test-only dependencies come from their own lock, so requirements.lock (a frozen field) never changes for them
    assert steps["Install test-only dependencies (lockfile)"]["run"] == "python -m pip install -r requirements-test.lock"
    names = [s.get("name", "") for s in test["steps"]]
    assert names.index("Install dependencies (lockfile)") < names.index("Install test-only dependencies (lockfile)") < names.index("Tests (no live LLM)")
    assert '-m "not live"' in steps["Tests (no live LLM)"]["run"] and "--junitxml" in steps["Tests (no live LLM)"]["run"]
    assert steps["Phase 0 acceptance matrix"]["run"] == "python -m benchmark.matrix"
    assert steps["Upload evidence on failure"]["if"] == "failure()"
    canary = ci["jobs"]["canary"]
    assert canary["continue-on-error"] is True and canary["runs-on"] == "ubuntu-latest"
    canary_setup = next(s for s in canary["steps"] if "setup-python" in s.get("uses", ""))
    assert canary_setup["with"] == {"python-version": "3.14", "allow-prereleases": True}
    assert any("requirements.lock" not in s.get("run", "") and "pip install -e" in s.get("run", "") for s in canary["steps"])


def test_python_version_file_matches_the_lockfile_environment():
    assert (REPO / ".python-version").read_text(encoding="utf-8").strip() == "3.11"
