"""Cross-validation decision table (spec v3 §6.2 and evaluation.differential.decide), every input enumerated.

The input space is small (5 bug-build outcomes x 5 clean-build outcomes x bug enabled or not), so it is listed in
full here instead of being sampled. MISSING = the test is absent from that build's results.
"""

from __future__ import annotations

import pytest

from evaluation.differential import decide

OUTCOMES = ("PASS", "FAIL", "ERROR", "SKIP", "MISSING")

# (bug build, clean build) -> (decision, rule), one row per pair, written out rather than computed.
WITH_BUG = {
    ("PASS", "PASS"): ("NOT_DETECTED", None),   ("PASS", "FAIL"): ("BROKEN", "R13"),    ("PASS", "ERROR"): ("BROKEN", "R13"),
    ("PASS", "SKIP"): ("NOT_DETECTED", None),   ("PASS", "MISSING"): ("BROKEN", "MISSING"),
    ("FAIL", "PASS"): ("DETECTED", "R11"),      ("FAIL", "FAIL"): ("BROKEN", "R12"),    ("FAIL", "ERROR"): ("BROKEN", "R12"),
    ("FAIL", "SKIP"): ("NOT_DETECTED", None),   ("FAIL", "MISSING"): ("BROKEN", "MISSING"),
    ("ERROR", "PASS"): ("BROKEN", "R10"),       ("ERROR", "FAIL"): ("BROKEN", "R10"),   ("ERROR", "ERROR"): ("BROKEN", "R10"),
    ("ERROR", "SKIP"): ("BROKEN", "R10"),       ("ERROR", "MISSING"): ("BROKEN", "MISSING"),
    ("SKIP", "PASS"): ("NOT_DETECTED", None),   ("SKIP", "FAIL"): ("NOT_DETECTED", None), ("SKIP", "ERROR"): ("NOT_DETECTED", None),
    ("SKIP", "SKIP"): ("NOT_DETECTED", None),   ("SKIP", "MISSING"): ("BROKEN", "MISSING"),
    ("MISSING", "PASS"): ("BROKEN", "MISSING"), ("MISSING", "FAIL"): ("BROKEN", "MISSING"), ("MISSING", "ERROR"): ("BROKEN", "MISSING"),
    ("MISSING", "SKIP"): ("BROKEN", "MISSING"), ("MISSING", "MISSING"): ("BROKEN", "MISSING"),
}  # fmt: skip
# Clean dataset: both builds are clean, so they must agree; DETECTED is impossible.
WITHOUT_BUG = {
    ("PASS", "PASS"): ("PASS", None),           ("PASS", "FAIL"): ("BROKEN", "R13"),    ("PASS", "ERROR"): ("BROKEN", "R13"),
    ("PASS", "SKIP"): ("NOT_DETECTED", None),   ("PASS", "MISSING"): ("BROKEN", "MISSING"),
    ("FAIL", "PASS"): ("BROKEN", "R13"),        ("FAIL", "FAIL"): ("BROKEN", "R12"),    ("FAIL", "ERROR"): ("BROKEN", "R12"),
    ("FAIL", "SKIP"): ("NOT_DETECTED", None),   ("FAIL", "MISSING"): ("BROKEN", "MISSING"),
    ("ERROR", "PASS"): ("BROKEN", "R10"),       ("ERROR", "FAIL"): ("BROKEN", "R10"),   ("ERROR", "ERROR"): ("BROKEN", "R10"),
    ("ERROR", "SKIP"): ("BROKEN", "R10"),       ("ERROR", "MISSING"): ("BROKEN", "MISSING"),
    ("SKIP", "PASS"): ("NOT_DETECTED", None),   ("SKIP", "FAIL"): ("NOT_DETECTED", None), ("SKIP", "ERROR"): ("NOT_DETECTED", None),
    ("SKIP", "SKIP"): ("NOT_DETECTED", None),   ("SKIP", "MISSING"): ("BROKEN", "MISSING"),
    ("MISSING", "PASS"): ("BROKEN", "MISSING"), ("MISSING", "FAIL"): ("BROKEN", "MISSING"), ("MISSING", "ERROR"): ("BROKEN", "MISSING"),
    ("MISSING", "SKIP"): ("BROKEN", "MISSING"), ("MISSING", "MISSING"): ("BROKEN", "MISSING"),
}  # fmt: skip


def _result(outcome: str) -> dict | None:
    return None if outcome == "MISSING" else {"outcome": outcome, "message": f"{outcome.lower()} message"}


def test_the_table_covers_every_input():
    assert set(WITH_BUG) == set(WITHOUT_BUG) == {(b, c) for b in OUTCOMES for c in OUTCOMES}


@pytest.mark.parametrize("bugs_enabled", [True, False], ids=["bug", "clean-dataset"])
@pytest.mark.parametrize("bug, clean", [(b, c) for b in OUTCOMES for c in OUTCOMES])
def test_every_pair_of_build_outcomes(bug, clean, bugs_enabled):
    d = decide("generated/test_x.py::test_a", _result(bug), _result(clean), bugs_enabled=bugs_enabled)
    expected = (WITH_BUG if bugs_enabled else WITHOUT_BUG)[(bug, clean)]
    assert (d.decision, d.rule) == expected
    assert (d.bug_outcome, d.clean_outcome) == (bug, clean)
    if not bugs_enabled:
        assert d.decision != "DETECTED"
