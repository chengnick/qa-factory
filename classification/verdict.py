"""Verdict aggregation (spec v3 §5.5 as amended in Phase 3; §6.3 wins where they conflicted).

Order, first match wins:
    ENV_BLOCKED   any PROVIDER or ENV classification
    AGENT_FAILED  any AGENT classification
    DEFECT_FOUND  any SUT classification (R11; R11U in surface mode), even if some tests are broken (§6.3)
    TEST_BROKEN   any TEST or HARNESS classification
    INCONCLUSIVE  any UNKNOWN classification (no rule matched)
    MISSED        evaluation mode, bug(s) enabled, cross-validation complete, nothing found
    FLAKY         a failed attempt was followed by a successful one (underlying verdict kept)
    PASS
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from classification.classifier import Classification, classify
from classification.observations import Observations

ORDER = ("ENV_BLOCKED", "AGENT_FAILED", "DEFECT_FOUND", "TEST_BROKEN", "INCONCLUSIVE", "MISSED", "FLAKY", "PASS")


@dataclass
class Outcome:
    verdict: str
    underlying_verdict: str | None
    decided_by: Classification | None
    classifications: list[Classification] = field(default_factory=list)
    flaky: bool = False
    flaky_evidence: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, Any]:
        layers = Counter(c.layer for c in self.classifications)
        rules = Counter(c.matched_rule or "UNKNOWN" for c in self.classifications)
        return {"total": len(self.classifications), "unknown": layers.get("UNKNOWN", 0), "layers": dict(layers), "rules": dict(rules)}

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "underlying_verdict": self.underlying_verdict,
            "decided_by": self.decided_by.to_json() if self.decided_by else None,
            "flaky": self.flaky,
            "flaky_evidence": self.flaky_evidence,
            "counts": self.counts,
            "classifications": [c.to_json() for c in self.classifications],
        }


def aggregate(classifications: Sequence[Classification], *, flaky: bool, missed_possible: bool, flaky_evidence: Sequence[str] = ()) -> Outcome:
    def first(*layers: str) -> Classification | None:
        return next((c for c in classifications if c.layer in layers), None)

    for verdict, layers in (
        ("ENV_BLOCKED", ("PROVIDER", "ENV")),
        ("AGENT_FAILED", ("AGENT",)),
        ("DEFECT_FOUND", ("SUT",)),
        ("TEST_BROKEN", ("TEST", "HARNESS")),
        ("INCONCLUSIVE", ("UNKNOWN",)),
    ):
        if (c := first(*layers)) is not None:
            return Outcome(verdict, None, c, list(classifications), flaky, list(flaky_evidence))
    if missed_possible:
        return Outcome("MISSED", None, None, list(classifications), flaky, list(flaky_evidence))
    if flaky:
        return Outcome("FLAKY", "PASS", None, list(classifications), flaky, list(flaky_evidence))
    return Outcome("PASS", None, None, list(classifications), flaky, list(flaky_evidence))


def surface_outcome(obs: Observations) -> Outcome:
    """Unverified verdict: what the pipeline alone can say (assertion failures count as SUT, R11U)."""
    return aggregate(classify(obs.surface), flaky=obs.flaky, missed_possible=False, flaky_evidence=obs.flaky_evidence)


def final_outcome(obs: Observations, *, bugs_enabled: bool) -> Outcome:
    """Cross-validated verdict: QA test units are replaced by the differential's per-test decisions."""
    units = [u for u in obs.surface if u.kind != "test"] + obs.evaluation
    diff = obs.differential or {}
    missed_possible = bugs_enabled and diff.get("status") == "COMPLETE"
    return aggregate(classify(units), flaky=obs.flaky, missed_possible=missed_possible, flaky_evidence=obs.flaky_evidence)
