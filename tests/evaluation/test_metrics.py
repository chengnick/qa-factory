"""§11.2 metrics: per-round mean/min/max, pooled counts, ENV_BLOCKED excluded from denominators."""

import pytest

from evaluation.metrics import compute


def run(rnd, bugs, verdict, surface, health=(1, 1), tokens=100):
    diff = None if verdict == "ENV_BLOCKED" else {"test_health": {"healthy": health[0], "total": health[1]}}
    return {"round": rnd, "sut_bugs": bugs, "verdict": verdict, "surface_verdict": surface, "differential": diff,
            "tokens": {"total": tokens}, "duration_s": 10.0}  # fmt: skip


RUNS = [
    # round 1: B02 found, B03 missed (surface said found), clean surface false positive
    run(1, ["B02"], "DEFECT_FOUND", "DEFECT_FOUND", (3, 4)),
    run(1, ["B03"], "MISSED", "DEFECT_FOUND", (2, 2)),
    run(1, [], "TEST_BROKEN", "DEFECT_FOUND", (1, 3)),
    # round 2: B02 found, B03 env-blocked (excluded), clean pass
    run(2, ["B02"], "DEFECT_FOUND", "DEFECT_FOUND", (4, 4)),
    run(2, ["B03"], "ENV_BLOCKED", "ENV_BLOCKED"),
    run(2, [], "PASS", "PASS", (2, 2)),
]


def test_detection_rates_per_round_and_pooled():
    m = compute(RUNS)
    true, surface = m["true_detection_rate"], m["surface_detection_rate"]
    assert true["per_round"] == {1: 0.5, 2: 1.0} and true["mean"] == 0.75 and (true["min"], true["max"]) == (0.5, 1.0)
    assert true["pooled"] == "2/3"  # the ENV_BLOCKED run is not in the denominator
    assert surface["pooled"] == "3/3"


def test_false_positive_rates():
    m = compute(RUNS)
    assert m["false_positive_rate_surface"]["pooled"] == "1/2"
    assert m["false_positive_rate_verified"]["pooled"] == "0/2"


def test_test_health_excludes_env_blocked_runs():
    m = compute(RUNS)
    assert m["test_health"]["pooled"] == "12/15"
    assert m["test_health"]["per_round"][1] == pytest.approx(6 / 9)


def test_env_blocked_rate_counts_all_runs():
    assert compute(RUNS)["env_blocked_rate"]["pooled"] == "1/6"


def test_per_bug_detection():
    per_bug = compute(RUNS)["per_bug_detection"]
    assert per_bug["B02"] == {"verified": "2/2", "completed": "2/2", "agent_failed": "0/2", "surface": "2/2", "env_blocked": "0/2"}
    assert per_bug["B03"] == {"verified": "0/1", "completed": "0/1", "agent_failed": "0/1", "surface": "1/1", "env_blocked": "1/2"}


def test_round_with_empty_denominator_is_not_averaged_as_zero():
    runs = [run(1, ["B02"], "DEFECT_FOUND", "DEFECT_FOUND"), run(2, ["B02"], "ENV_BLOCKED", "ENV_BLOCKED")]
    stat = compute(runs)["true_detection_rate"]
    assert stat["per_round"] == {1: 1.0} and stat["mean"] == 1.0 and stat["n_rounds"] == 1


@pytest.mark.parametrize(
    "num, den, low, high",
    [(12, 15, 0.548, 0.930), (0, 15, 0.0, 0.204), (15, 15, 0.796, 1.0), (1, 15, 0.012, 0.298), (5, 5, 0.566, 1.0)],
)
def test_wilson_interval_matches_reference_values(num, den, low, high):
    from evaluation.metrics import wilson_interval

    lo, hi = wilson_interval(num, den)
    assert lo == pytest.approx(low, abs=1e-3) and hi == pytest.approx(high, abs=1e-3)


def test_wilson_interval_undefined_for_empty_denominator():
    from evaluation.metrics import wilson_interval

    assert wilson_interval(0, 0) is None


def test_every_rate_carries_a_ci_on_its_pooled_count():
    m = compute(RUNS)
    assert m["true_detection_rate"]["ci95"] == pytest.approx([0.2077, 0.9385], abs=1e-3)  # 2/3
    assert m["env_blocked_rate"]["ci95"][0] == pytest.approx(0.0301, abs=1e-3)  # 1/6


def test_detection_when_pipeline_completed_excludes_agent_failed():
    runs = RUNS + [run(3, ["B03"], "AGENT_FAILED", "AGENT_FAILED"), run(3, ["B02"], "DEFECT_FOUND", "DEFECT_FOUND")]
    m = compute(runs)
    assert m["true_detection_rate"]["pooled"] == "3/5"  # AGENT_FAILED counts as not found
    assert m["true_detection_rate_completed"]["pooled"] == "3/4"  # only runs that produced tests
    assert m["per_bug_detection"]["B03"]["verified"] == "0/2"
    assert m["per_bug_detection"]["B03"]["completed"] == "0/1"
    assert m["per_bug_detection"]["B03"]["agent_failed"] == "1/2"


def test_unknown_and_inconclusive_rates():
    classified = [
        {**run(1, ["B02"], "INCONCLUSIVE", "INCONCLUSIVE"), "classification": {"counts": {"total": 2, "unknown": 1}}},
        {**run(1, [], "PASS", "PASS"), "classification": {"counts": {"total": 0, "unknown": 0}}},
    ]
    m = compute(RUNS + classified)
    assert m["unknown_classification_rate"]["pooled"] == "1/2"
    assert m["unknown_classification_rate"]["runs_with_classification"] == 2
    assert m["inconclusive_rate"]["pooled"] == "1/7"  # the ENV_BLOCKED run is excluded


def test_harness_failure_run_is_not_in_the_test_health_denominator():
    """An R20 run (LLM rejected our request, HARNESS) ends before any test exists: no cross-validation,
    so it adds nothing to test health (neither healthy nor total), whatever its verdict."""
    r20 = {**run(3, ["B04"], "TEST_BROKEN", "TEST_BROKEN"), "differential": None,
           "classification": {"counts": {"total": 1, "unknown": 0}, "decided_by": {"matched_rule": "R20"}}}  # fmt: skip
    assert compute(RUNS + [r20])["test_health"]["pooled"] == compute(RUNS)["test_health"]["pooled"] == "12/15"
    assert 3 not in compute(RUNS + [r20])["test_health"]["per_round"]
