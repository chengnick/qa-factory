"""Every startup validation error of spec v3.1 §8.5.3 stops with a located message; nothing falls back to defaults."""

from __future__ import annotations

import copy

import pytest

import app
from evaluation import run as runner
from permissions.policy import PolicyError, load_policy
from tests.policy.support import default_raw, write_policy


def _set(raw: dict, dotted: str, value) -> None:
    *parents, last = dotted.split(".")
    node = raw
    for key in parents:
        node = node[key]
    node[last] = value


def _del(raw: dict, dotted: str) -> None:
    *parents, last = dotted.split(".")
    node = raw
    for key in parents:
        node = node[key]
    del node[last]


CASES = [
    # (id, mutation, expected fragment of the error message)
    ("unknown field", lambda r: _set(r, "agents.qa.tools.pytest", {"retries": 3}), "agents.qa.tools.pytest.retries"),
    ("unknown top-level field", lambda r: _set(r, "mode", "lenient"), "mode"),
    ("unknown agent", lambda r: _set(r, "agents.qa_agent", {"tools": {}}), "agents.qa_agent: unknown agent"),
    ("pipeline agent missing", lambda r: _del(r, "agents.report"), "agents.report: pipeline agent missing"),
    ("unknown tool", lambda r: _set(r, "agents.qa.tools.shell", {}), "agents.qa.tools.shell"),
    ("condition type", lambda r: _set(r, "agents.automation.tools.file_write.path_prefix", 123), "agents.automation.tools.file_write.path_prefix"),
    ("allowlist type", lambda r: _set(r, "agents.qa.tools.http_request.url_allowlist", "{sut_base_url}"), "url_allowlist"),
    ("condition on runner", lambda r: _set(r, "agents.qa.tools.pytest", {"path_prefix": "x"}), "agents.qa.tools.pytest.path_prefix"),
    ("undefined placeholder", lambda r: _set(r, "agents.automation.tools.file_write.path_prefix", "artifacts/{home}/x/"), "undefined placeholder {home}"),
    ("extra placeholder declared", lambda r: r["placeholders"].append("home"), "only ['run_id', 'sut_base_url'] are allowed"),
    ("write area outside artifacts", lambda r: _set(r, "agents.automation.tools.file_write.path_prefix", "generated/{run_id}/"), "must be under artifacts/"),
    ("write area without run_id", lambda r: _set(r, "agents.automation.tools.file_write.path_prefix", "artifacts/generated/"), "must contain {run_id}"),
    ("evidence without artifacts", lambda r: _set(r, "paths.evidence", ["benchmark/", "traces/"]), "paths.evidence: must contain 'artifacts/'"),
    ("schema version", lambda r: _set(r, "schema", 2), "schema"),
    ("missing section", lambda r: _del(r, "generated_code"), "generated_code"),
    ("boolean instead of object", lambda r: _set(r, "agents.qa.tools.pytest", True), "agents.qa.tools.pytest"),
]


@pytest.mark.parametrize("mutate, fragment", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_invalid_policy_is_rejected_with_location(tmp_dir, mutate, fragment):
    raw = copy.deepcopy(default_raw())
    mutate(raw)
    with pytest.raises(PolicyError) as exc_info:
        load_policy(write_policy(tmp_dir, raw))
    assert fragment in str(exc_info.value)


def test_yaml_syntax_error_reports_line(tmp_dir):
    path = write_policy(tmp_dir, "schema: 1\nagents:\n  qa: [unclosed\n")
    with pytest.raises(PolicyError, match=r"YAML syntax error \(line \d+, column \d+\)"):
        load_policy(path)


def test_missing_file(tmp_dir):
    with pytest.raises(PolicyError, match="cannot read policy"):
        load_policy(tmp_dir / "nope.yaml")


def test_app_stops_before_any_run(tmp_dir, capsys):
    bad = write_policy(tmp_dir, "schema: 1\n")
    code = app.main(["--requirement", "REQ-005", "--llm", "fake", "--policy", str(bad), "--artifacts-dir", str(tmp_dir / "artifacts")])
    assert code == 2
    assert not (tmp_dir / "artifacts").exists()  # no run_id, no workspace: a startup error, not a failed run
    assert "policy error" in capsys.readouterr().err


def test_evaluation_runner_stops_before_any_run(tmp_dir):
    bad = write_policy(tmp_dir, "schema: 1\n")
    code = runner.main(["--dataset", "dev", "--llm", "fake", "--policy", str(bad),
                        "--results-dir", str(tmp_dir / "r"), "--artifacts-dir", str(tmp_dir / "a")])  # fmt: skip
    assert code == 2
    assert not (tmp_dir / "a").exists() and not (tmp_dir / "r").exists()
