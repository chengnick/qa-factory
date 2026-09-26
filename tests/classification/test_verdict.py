"""Verdict aggregation order (Phase 3): ENV_BLOCKED > AGENT_FAILED > DEFECT_FOUND > TEST_BROKEN > INCONCLUSIVE
> MISSED > FLAKY > PASS."""

import pytest

from classification.classifier import Classification
from classification.verdict import ORDER, aggregate


def c(layer, rule="Rx"):
    return Classification("u", layer, "S", rule, "evidence")


@pytest.mark.parametrize(
    "layers, verdict",
    [
        (["PROVIDER", "AGENT", "SUT"], "ENV_BLOCKED"),
        (["ENV", "TEST"], "ENV_BLOCKED"),
        (["AGENT", "SUT", "TEST"], "AGENT_FAILED"),
        (["TEST", "SUT", "UNKNOWN"], "DEFECT_FOUND"),  # §6.3: found even with broken tests
        (["HARNESS", "UNKNOWN"], "TEST_BROKEN"),
        (["UNKNOWN"], "INCONCLUSIVE"),
    ],
)
def test_layer_precedence(layers, verdict):
    outcome = aggregate([c(layer) for layer in layers], flaky=True, missed_possible=True)
    assert outcome.verdict == verdict
    assert outcome.decided_by.layer in layers


def test_missed_only_without_any_failure():
    assert aggregate([], flaky=False, missed_possible=True).verdict == "MISSED"
    assert aggregate([c("TEST")], flaky=False, missed_possible=True).verdict == "TEST_BROKEN"


def test_missed_beats_flaky():
    assert aggregate([], flaky=True, missed_possible=True).verdict == "MISSED"


def test_flaky_keeps_the_underlying_verdict():
    outcome = aggregate([], flaky=True, missed_possible=False, flaky_evidence=["tool.pytest attempt 1 failed"])
    assert (outcome.verdict, outcome.underlying_verdict) == ("FLAKY", "PASS")
    assert outcome.flaky_evidence == ["tool.pytest attempt 1 failed"]


def test_flaky_does_not_hide_a_defect():
    outcome = aggregate([c("SUT", "R11")], flaky=True, missed_possible=False)
    assert outcome.verdict == "DEFECT_FOUND" and outcome.flaky is True


def test_pass():
    assert aggregate([], flaky=False, missed_possible=False).verdict == "PASS"


def test_order_constant_matches_spec():
    assert ORDER == ("ENV_BLOCKED", "AGENT_FAILED", "DEFECT_FOUND", "TEST_BROKEN", "INCONCLUSIVE", "MISSED", "FLAKY", "PASS")


def test_counts_report_unknowns():
    outcome = aggregate([c("UNKNOWN", None), c("TEST", "R10")], flaky=False, missed_possible=False)
    assert outcome.counts["unknown"] == 1 and outcome.counts["rules"] == {"UNKNOWN": 1, "R10": 1}
