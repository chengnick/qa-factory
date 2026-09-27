"""The runner's W05 step: workflow_eval.json, a WORKFLOW_VIOLATION event per missing file, meta updated."""

from __future__ import annotations

import json

from evaluation.run import record_workflow
from evaluation.workflow import workflow_json


def test_missing_evidence_in_acceptance_mode_is_recorded_everywhere(tmp_dir):
    run = tmp_dir / "RUN-20260927-120000-ABCD"
    run.mkdir()
    (run / "security_events.json").write_text(json.dumps({"run_id": run.name, "breach": False, "events": []}), encoding="utf-8")
    meta = {"run_id": run.name, "evaluation_mode": True, "differential": None}
    (run / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    record_workflow(run, meta, workflow_json(run.name, [], False, rounds=0))

    workflow = json.loads((run / "workflow_eval.json").read_text(encoding="utf-8"))
    assert workflow["workflow_status"] == "FAIL"
    assert workflow["missing_evidence"] == ["trace.json", "classification.json", "rounds.json"]
    assert [v["rule"] for v in workflow["violations"]] == ["W05"] * 3
    events = json.loads((run / "security_events.json").read_text(encoding="utf-8"))["events"]
    assert [(e["type"], e["action"], e["target"], e["executed"]) for e in events] == [
        ("WORKFLOW_VIOLATION", "W05", "trace.json", False),
        ("WORKFLOW_VIOLATION", "W05", "classification.json", False),
        ("WORKFLOW_VIOLATION", "W05", "rounds.json", False),
    ]
    saved = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    assert saved["workflow"] == {"status": "FAIL", "goal_drift": False, "violations": ["W05"] * 3, "missing_evidence": 3}
    assert saved["security"]["types"] == ["WORKFLOW_VIOLATION"]


def test_pipeline_violations_are_kept_and_w05_added(tmp_dir):
    run = tmp_dir / "run"
    run.mkdir()
    meta = {"run_id": "run", "evaluation_mode": False}
    pipeline_part = {**workflow_json("run", [], True, rounds=2), "violations": [{"rule": "W01", "evidence": "e"}], "workflow_status": "FAIL"}

    record_workflow(run, meta, pipeline_part)

    workflow = json.loads((run / "workflow_eval.json").read_text(encoding="utf-8"))
    assert [v["rule"] for v in workflow["violations"]] == ["W01"]  # outside acceptance mode W05 adds nothing
    assert workflow["goal_drift"] is True and workflow["workflow_status"] == "FAIL" and workflow["rounds"] == 2
    assert not (run / "security_events.json").exists()  # nothing to append to; never created by W05
