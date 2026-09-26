"""Rule table: every rule is reachable (its own case matches it and nothing earlier), ordering is enforced."""

import pytest

from classification.classifier import classify_unit, match
from classification.observations import Unit
from classification.rules import RULES

# One case per rule: the classifier must pick exactly this rule for it (reachability, spec v3 §5.4 + Phase 3).
CASES: dict[str, Unit] = {
    "R1": Unit("health", tool="http_request", exception="ToolConnectionError", message="GET /health: ConnectError", route="/health"),
    "R2": Unit("llm", exception="LLMRateLimitError", message="Gemini API error 429"),
    "R3": Unit("llm", exception="LLMUnavailableError", message="Gemini API error 503"),
    "R4": Unit("llm", exception="LLMTimeoutError", message="timed out"),
    "R5": Unit("agent", agent="automation", exception="AgentOutputError", message="LLM output is not valid JSON"),
    "R6": Unit("tool", tool="rm_rf", exception="UnknownToolError", message="tool 'rm_rf' is not registered"),
    "R7": Unit("agent", agent="test_design", exception="HandoffError", message="acceptance_criteria missing", upstream="requirement"),
    "R18": Unit("tool", agent="qa", tool="file_write", exception="PermissionDeniedError", message="qa may not call file_write"),
    "R9": Unit("tool", tool="pytest", exit_code=2, collection_error=True, message="1 error"),
    "R8": Unit("tool", tool="pytest", exit_code=4, message="usage error"),
    "R17": Unit("tool", tool="pytest", exception="ToolTimeoutError", message="pytest did not finish within 120s"),
    "R14": Unit("test", tool="playwright", test_id="t::ui", outcome="ERROR", health_ok=True,
                message="TimeoutError: Locator.click: Timeout 5000ms exceeded"),  # fmt: skip
    "R15": Unit("test", tool="playwright", test_id="t::ui", outcome="ERROR", health_ok=False,
                message="TimeoutError: page.goto: Timeout 30000ms exceeded"),  # fmt: skip
    "R16": Unit("test", tool="playwright", test_id="t::ui", outcome="ERROR",
                message="Error: BrowserType.launch: Executable doesn't exist at ms-playwright/chromium"),  # fmt: skip
    "R10": Unit("test", tool="pytest", test_id="t::a", outcome="ERROR", message="AttributeError: 'function' object has no attribute 'post'"),
    "R11": Unit("diff", test_id="t::a", outcome="FAIL", decision_rule="R11", message="bug build: assert 200 == 409"),
    "R11U": Unit("test", tool="pytest", test_id="t::a", outcome="FAIL", message="AssertionError: assert 200 == 409"),
    "R12": Unit("diff", test_id="t::a", outcome="FAIL", decision_rule="R12", message="fails on both builds"),
    "R13": Unit("diff", test_id="t::a", outcome="PASS", decision_rule="R13", message="clean build: assert 409 == 200"),
}

EXPECTED_ORDER = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R18", "R9", "R8", "R17", "R14", "R15", "R16", "R10", "R11", "R11U", "R12", "R13"]


def test_every_rule_has_a_reachability_case():
    assert set(CASES) == {r.id for r in RULES}


@pytest.mark.parametrize("rule_id", [r.id for r in RULES])
def test_rule_is_reachable(rule_id):
    classification = classify_unit(CASES[rule_id])
    assert classification.matched_rule == rule_id
    rule = next(r for r in RULES if r.id == rule_id)
    assert (classification.layer, classification.symptom) == (rule.layer, rule.symptom_for(CASES[rule_id]))
    assert classification.evidence


def test_rule_order_is_specific_before_general():
    assert [r.id for r in RULES] == EXPECTED_ORDER


def test_collection_error_beats_exit_code_rule():
    """R9 sits before R8: a collection failure (pytest exit 2) is a TEST problem, not a HARNESS one."""
    unit = Unit("tool", tool="pytest", exit_code=2, collection_error=True)
    assert match(unit).id == "R9"


@pytest.mark.parametrize("rule_id", ["R14", "R15", "R16"])
def test_playwright_rules_beat_the_generic_non_assertion_rule(rule_id):
    """R14-R16 sit before R10: Playwright errors are non-assertion exceptions and would otherwise all be R10."""
    assert CASES[rule_id].outcome == "ERROR"
    assert match(CASES[rule_id]).id == rule_id


def test_playwright_rules_also_apply_to_cross_validated_tests():
    unit = Unit("diff", test_id="t::ui", outcome="ERROR", decision_rule="R10", health_ok=True, message="TimeoutError: Locator.fill: Timeout 5000ms")
    assert match(unit).id == "R14"


@pytest.mark.parametrize(
    "unit, symptom",
    [
        (Unit("llm", exception="LLMTimeoutError"), "TIMEOUT"),
        (Unit("llm", exception="LLMConnectionError"), "CONNECTION"),
        (Unit("diff", decision_rule="R11", message="bug build: assert 500 == 422"), "HTTP_5XX"),
        (Unit("diff", decision_rule="R11", message="bug build: assert 200 == 403"), "ASSERTION"),
    ],
)
def test_symptoms_depend_on_evidence(unit, symptom):
    assert classify_unit(unit).symptom == symptom


def test_handoff_failure_is_attributed_to_the_upstream_agent():
    c = classify_unit(CASES["R7"])
    assert c.agent == "requirement" and "upstream agent: requirement" in c.evidence


def test_unmatched_unit_is_unknown_with_evidence():
    c = classify_unit(Unit("agent", agent="qa", exception="KeyError", message="'x'"))
    assert (c.layer, c.symptom, c.matched_rule) == ("UNKNOWN", "NONE", None)
    assert "KeyError" in c.evidence


def test_r11u_is_flagged_unverified():
    assert classify_unit(CASES["R11U"]).unverified is True
    assert classify_unit(CASES["R11"]).unverified is False


def test_evidence_is_redacted():
    unit = Unit("llm", exception="LLMRateLimitError", message="quota for key AIzaSyA1234567890abcdefghijklmnopqrstuv")
    assert "AIza" not in classify_unit(unit).evidence


@pytest.mark.parametrize(
    "message, symptom",
    [
        ("AssertionError: Internal Server Error\nassert 500 == 422", "HTTP_5XX"),
        ("assert r.status_code == 503", "HTTP_5XX"),
        ("where 500 = <Response [500 Internal Server Error]>", "HTTP_5XX"),
        # Phase 2R RUN-20260925-160630-19B8: a 200-vs-403 failure whose body holds a timestamp with "530"
        ('AssertionError: {"id":2,"created_at":"2026-09-25T16:06:50.530+00:00"}\nassert 200 == 403', "ASSERTION"),
        ("assert 409 == 200", "ASSERTION"),
    ],
)
def test_http_5xx_symptom_only_from_the_failed_comparison(message, symptom):
    assert classify_unit(Unit("test", test_id="t::a", outcome="FAIL", message=message)).symptom == symptom
    assert classify_unit(Unit("diff", test_id="t::a", outcome="FAIL", decision_rule="R11", message=message)).symptom == symptom
