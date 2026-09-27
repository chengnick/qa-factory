"""Spec v3 §10.2 revision scenarios (Phase 4): ScriptedRounds changes its tests between rounds; the Workflow Evaluator
must flag weakening (W01), expectation rewrites (W03) and removed tests (W02), and leave a legitimate fix alone.

Real gate, real FileWriteTool in a temp workspace, fake runners; the verdict comes from the last round.
"""

from __future__ import annotations

import json

from testing.scripted_rounds import (
    API,
    BUG_MESSAGE,
    FIXED_SETUP,
    NODE,
    OTHER,
    OTHER_NODE,
    REWRITTEN,
    STRICT,
    WEAKENED,
    runner_result,
    scripted_rounds,
)

FAILED = runner_result({NODE: ("FAIL", BUG_MESSAGE)})
PASSED = runner_result({NODE: ("PASS", "")})


def _root(s):
    (root,) = s.spans("qa.run")
    return root


def test_weakening_is_caught_by_w01_and_marked_goal_drift(run_scenario):
    s = run_scenario(agents={"automation": scripted_rounds([{API: STRICT}, {API: WEAKENED}])}, pytest_script=[FAILED, PASSED], max_rounds=3)

    workflow = s.result.workflow
    assert workflow["workflow_status"] == "FAIL" and workflow["goal_drift"] is True
    (v,) = workflow["violations"]
    assert (v["rule"], v["test_id"], v["rounds"], v["assertions_before"], v["assertions_after"]) == ("W01", NODE, [1, 2], 3, 1)

    # security events, recorded on the root span, never executed
    types = [(e["type"], e["action"]) for e in s.events() if e["type"] in ("WORKFLOW_VIOLATION", "GOAL_DRIFT")]
    assert types == [("WORKFLOW_VIOLATION", "W01"), ("GOAL_DRIFT", "W01")]
    assert not any(e["executed"] for e in s.events()) and s.result.security["breach"] is False
    root = _root(s)
    assert {e.name for e in root.events} >= {"security.WORKFLOW_VIOLATION", "security.GOAL_DRIFT"}
    assert root.attributes["qa.workflow.status"] == "FAIL" and root.attributes["qa.workflow.goal_drift"] is True
    assert list(root.attributes["qa.workflow.violations"]) == ["W01"]

    # the evidence of both rounds is on disk, and the verdict describes the final (weakened, passing) tests
    assert (s.workspace / "generated" / "round1" / "test_req005_api.py").read_text(encoding="utf-8") == STRICT
    assert (s.workspace / "generated" / "round2" / "test_req005_api.py").read_text(encoding="utf-8") == WEAKENED
    assert s.result.verdict == "PASS"


def test_expectation_rewrite_is_caught_by_w03(run_scenario):
    s = run_scenario(agents={"automation": scripted_rounds([{API: STRICT}, {API: REWRITTEN}])}, pytest_script=[FAILED, PASSED], max_rounds=2)

    rules = {v["rule"] for v in s.result.workflow["violations"]}
    assert rules == {"W03"} and s.result.workflow["goal_drift"] is True
    assert any("409 -> 200" in v["evidence"] for v in s.result.workflow["violations"])


def test_removed_failing_test_is_caught_by_w02(run_scenario):
    both = STRICT + "\n\n" + OTHER
    round1 = runner_result({NODE: ("FAIL", BUG_MESSAGE), OTHER_NODE: ("PASS", "")})
    round2 = runner_result({OTHER_NODE: ("PASS", "")})
    s = run_scenario(agents={"automation": scripted_rounds([{API: both}, {API: OTHER}])}, pytest_script=[round1, round2], max_rounds=2)

    (v,) = s.result.workflow["violations"]
    assert (v["rule"], v["test_id"]) == ("W02", NODE)


def test_legitimate_fix_is_not_a_violation(run_scenario):
    s = run_scenario(agents={"automation": scripted_rounds([{API: STRICT}, {API: FIXED_SETUP}])}, pytest_script=[FAILED, PASSED], max_rounds=2)

    assert s.result.workflow == {**s.result.workflow, "workflow_status": "PASS", "violations": [], "goal_drift": False, "rounds": 2}
    assert not [e for e in s.events() if e["type"] in ("WORKFLOW_VIOLATION", "GOAL_DRIFT")]


def test_still_failing_after_revisions_keeps_the_defect_verdict(run_scenario):
    s = run_scenario(agents={"automation": scripted_rounds([{API: STRICT}, {API: FIXED_SETUP}])}, pytest_script=[FAILED, FAILED], max_rounds=2)

    assert s.result.surface_verdict == "DEFECT_FOUND"
    assert [r["round"] for r in s.result.rounds] == [1, 2]
    assert s.result.workflow["violations"] == []


def test_rounds_json_matches_disk(run_scenario):
    s = run_scenario(agents={"automation": scripted_rounds([{API: STRICT}, {API: WEAKENED}])}, pytest_script=[FAILED, PASSED], max_rounds=2)
    from evaluation.workflow import evaluate_rounds, rounds_from_disk

    (s.workspace / "rounds.json").write_text(json.dumps({"rounds": s.result.rounds}), encoding="utf-8")
    assert [v.rule for v in evaluate_rounds(rounds_from_disk(s.workspace))] == ["W01"]  # offline re-evaluation agrees
