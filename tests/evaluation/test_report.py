"""report.json (spec v3 §12) is built from the run's own files; the CLI never writes into run directories."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.report import build_report, main


def _run_dir(root: Path) -> Path:
    run = root / "RUN-20260927-120000-ABCD"
    run.mkdir(parents=True)
    files = {
        "meta.json": {"run_id": run.name, "trace_id": "ab" * 16, "model": "m", "prompt_version": "v3", "dataset": "dev",
                      "sut_bugs": ["B02"], "git_commit": {"sha": "abc", "dirty": False}, "verdict": "DEFECT_FOUND",
                      "surface_verdict": "DEFECT_FOUND", "underlying_verdict": None},
        "classification.json": {"surface": {"flaky": False, "classifications": []},
                                "final": {"flaky": True, "classifications": [{"unit": "diff", "span": "tool.pytest", "layer": "SUT",
                                          "symptom": "ASSERTION", "matched_rule": "R11", "evidence": "e", "test_id": "t"}]}},
        "differential.json": {"status": "COMPLETE", "counts": {"detected": 1, "broken": 0, "missed": 2, "passed": 0, "tests": 3}},
        "security_events.json": {"breach": False, "events": [{"type": "PERMISSION_DENIED"}]},
        "workflow_eval.json": {"workflow_status": "PASS", "violations": [], "goal_drift": False, "rounds": 1, "missing_evidence": []},
        "trace.json": {"spans": [{"name": "attempt", "attributes": {"qa.retry.attempt": 1}},
                                 {"name": "attempt", "attributes": {"qa.retry.attempt": 2}},
                                 {"name": "tool.pytest", "attributes": {"qa.isolation.level": "L1"}}]},
    }  # fmt: skip
    for name, data in files.items():
        (run / name).write_text(json.dumps(data), encoding="utf-8")
    return run


def test_report_has_the_spec_fields(tmp_dir):
    report = build_report(_run_dir(tmp_dir))

    assert report["meta"]["git_commit"] == "abc" and report["meta"]["sut_bugs"] == ["B02"]
    assert report["verdict"] == "DEFECT_FOUND"
    assert report["differential"] == {"status": "COMPLETE", "detected": 1, "broken": 0, "missed": 2}
    assert report["attribution"] == [{"span": "tool.pytest", "layer": "SUT", "symptom": "ASSERTION", "matched_rule": "R11", "evidence": "e", "test_id": "t"}]
    assert report["reliability"] == {"retries": 1, "flaky": True}
    assert report["security"] == {"events": 1, "breach": False}
    assert report["workflow"] == {"workflow_status": "PASS", "violations": [], "goal_drift": False, "rounds": 1}
    assert report["isolation_level"] == "L1" and "not an OS sandbox" in report["isolation_note"]
    assert report["artifacts_complete"] is True


def test_older_runs_report_what_is_missing_as_unknown(tmp_dir):
    run = tmp_dir / "old"
    run.mkdir()
    (run / "meta.json").write_text(json.dumps({"run_id": "old", "verdict": "PASS"}), encoding="utf-8")
    report = build_report(run)
    assert report["verdict"] == "PASS"
    assert report["workflow"] is None and report["artifacts_complete"] is None and report["isolation_level"] is None


def test_cli_writes_only_to_out(tmp_dir, capsys):
    run = _run_dir(tmp_dir / "runs")
    before = sorted(p.name for p in run.iterdir())
    assert main([str(run), str(tmp_dir / "nothing-here"), "--out", str(tmp_dir / "out")]) == 0
    assert sorted(p.name for p in run.iterdir()) == before
    assert json.loads((tmp_dir / "out" / f"{run.name}.report.json").read_text(encoding="utf-8"))["run_id"] == run.name
    assert "skip" in capsys.readouterr().err
