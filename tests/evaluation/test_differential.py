"""Per-test and run-level cross-validation decisions (spec v3 §6.2, §6.3)."""

import pytest

from evaluation.differential import compare, decide, run_verdict


def _r(outcome, message=""):
    return {"node_id": "t", "outcome": outcome, "message": message}


@pytest.mark.parametrize(
    "bug, clean, decision, rule",
    [
        # the five rows of spec v3 §6.2
        (_r("FAIL", "assert 200 == 409"), _r("PASS"), "DETECTED", "R11"),
        (_r("FAIL", "assert 1 == 2"), _r("FAIL", "assert 1 == 2"), "BROKEN", "R12"),
        (_r("PASS"), _r("FAIL", "assert 409 == 200"), "BROKEN", "R13"),
        (_r("PASS"), _r("PASS"), "NOT_DETECTED", None),
        (_r("ERROR", "AttributeError: 'function' object has no attribute 'post'"), _r("PASS"), "BROKEN", "R10"),
        (_r("ERROR", "TypeError"), _r("ERROR", "TypeError"), "BROKEN", "R10"),
        # additions documented in decide()
        (_r("FAIL", "assert 200 == 409"), _r("ERROR", "fixture error"), "BROKEN", "R12"),
        (_r("PASS"), _r("ERROR", "fixture error"), "BROKEN", "R13"),
        (_r("SKIP"), _r("SKIP"), "NOT_DETECTED", None),
        (None, _r("PASS"), "BROKEN", "MISSING"),
        (_r("PASS"), None, "BROKEN", "MISSING"),
    ],
)
def test_decide_with_bug_enabled(bug, clean, decision, rule):
    d = decide("t", bug, clean, bugs_enabled=True)
    assert (d.decision, d.rule) == (decision, rule)


def test_r11_symptom_distinguishes_http_5xx():
    assert decide("t", _r("FAIL", "assert 500 == 422"), _r("PASS"), bugs_enabled=True).symptom == "HTTP_5XX"
    assert decide("t", _r("FAIL", "assert 200 == 403"), _r("PASS"), bugs_enabled=True).symptom == "ASSERTION"


@pytest.mark.parametrize(
    "bug, clean, decision, rule",
    [
        (_r("PASS"), _r("PASS"), "PASS", None),
        (_r("FAIL"), _r("FAIL"), "BROKEN", "R12"),
        (_r("FAIL"), _r("PASS"), "BROKEN", "R13"),  # two identical clean SUTs disagree: nondeterminism, never DETECTED
        (_r("PASS"), _r("FAIL"), "BROKEN", "R13"),
        (_r("ERROR"), _r("PASS"), "BROKEN", "R10"),
    ],
)
def test_decide_on_clean_dataset(bug, clean, decision, rule):
    d = decide("t", bug, clean, bugs_enabled=False)
    assert (d.decision, d.rule) == (decision, rule)


def test_compare_matches_by_node_id_not_position():
    bug = [{"node_id": "a", "outcome": "FAIL", "message": "x"}, {"node_id": "b", "outcome": "PASS", "message": ""}]
    clean = [{"node_id": "b", "outcome": "PASS", "message": ""}, {"node_id": "a", "outcome": "PASS", "message": ""}]

    decisions = {d.node_id: d.decision for d in compare(bug, clean, bugs_enabled=True)}

    assert decisions == {"a": "DETECTED", "b": "NOT_DETECTED"}


def _decisions(*kinds):
    table = {"DETECTED": (_r("FAIL"), _r("PASS")), "BROKEN": (_r("ERROR"), _r("PASS")), "NOT_DETECTED": (_r("PASS"), _r("PASS"))}
    return [decide(str(i), *table[k], bugs_enabled=True) for i, k in enumerate(kinds)]


@pytest.mark.parametrize(
    "kinds, verdict",
    [
        (["DETECTED", "NOT_DETECTED"], "DEFECT_FOUND"),
        (["DETECTED", "BROKEN"], "DEFECT_FOUND"),  # §6.3: still found; broken tests go to test_health
        (["NOT_DETECTED", "NOT_DETECTED"], "MISSED"),
        (["NOT_DETECTED", "BROKEN"], "TEST_BROKEN"),
        ([], "TEST_BROKEN"),
    ],
)
def test_run_verdict_with_bug(kinds, verdict):
    assert run_verdict(_decisions(*kinds), bugs_enabled=True) == verdict


def test_run_verdict_clean_dataset():
    ok = [decide("a", _r("PASS"), _r("PASS"), bugs_enabled=False)]
    broken = ok + [decide("b", _r("FAIL"), _r("FAIL"), bugs_enabled=False)]
    assert run_verdict(ok, bugs_enabled=False) == "PASS"
    assert run_verdict(broken, bugs_enabled=False) == "TEST_BROKEN"


def test_r11_symptom_ignores_5xx_digits_outside_the_comparison():
    message = 'AssertionError: {"created_at":"2026-09-25T16:06:50.530+00:00"}\nassert 200 == 403'
    assert decide("t", _r("FAIL", message), _r("PASS"), bugs_enabled=True).symptom == "ASSERTION"
