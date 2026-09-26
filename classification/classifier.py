"""Apply the rule table to classification units: first match wins; no match -> layer UNKNOWN.

Every classification carries `matched_rule` and `evidence` (the raw fragment that triggered it) and no
confidence value (spec v3 §5.4).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from classification.observations import Unit
from classification.rules import RULES, Rule
from observability.redact import redact

EVIDENCE_LIMIT = 300


@dataclass(frozen=True)
class Classification:
    unit: str
    layer: str
    symptom: str
    matched_rule: str | None
    evidence: str
    span_id: str | None = None
    span: str = ""
    agent: str | None = None
    test_id: str | None = None
    unverified: bool = False

    def to_json(self) -> dict:
        return asdict(self)


def _evidence(unit: Unit) -> str:
    parts = [
        unit.exception and f"{unit.exception}: {unit.message}" or unit.message,
        unit.test_id and f"test {unit.test_id} ({unit.outcome})",
        unit.exit_code is not None and unit.kind == "tool" and f"exit code {unit.exit_code}",
        unit.status_code is not None and f"HTTP {unit.status_code}",
        unit.decision_rule and f"cross-validation {unit.decision_rule}",
        unit.upstream and f"upstream agent: {unit.upstream}",
    ]
    text = " | ".join(p for p in parts if p)
    return redact(text)[:EVIDENCE_LIMIT] or unit.kind


def match(unit: Unit, rules: Iterable[Rule] = RULES) -> Rule | None:
    for rule in rules:
        if rule.when(unit):
            return rule
    return None


def classify_unit(unit: Unit) -> Classification:
    rule = match(unit)
    agent = unit.upstream if rule is not None and rule.id == "R7" and unit.upstream else unit.agent
    if rule is None:
        return Classification(unit.kind, "UNKNOWN", "NONE", None, _evidence(unit), unit.span_id, unit.span_name, agent, unit.test_id)
    return Classification(
        unit.kind, rule.layer, rule.symptom_for(unit), rule.id, _evidence(unit), unit.span_id, unit.span_name, agent, unit.test_id,
        unverified=rule.id == "R11U",
    )  # fmt: skip


def classify(units: Iterable[Unit]) -> list[Classification]:
    return [classify_unit(u) for u in units]
