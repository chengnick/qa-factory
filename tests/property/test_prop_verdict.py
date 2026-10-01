"""Property 4: verdict aggregation (spec v3 §5.5).

- A run in which no test was executed is never PASS.
- The order of the observations does not change the verdict.
- One more test that passes on both builds does not change DEFECT_FOUND.
- The verdict is always the highest-priority one present (classification.verdict.ORDER).
"""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

import classification.verdict as verdict_mod
from classification.classifier import Classification
from classification.observations import observe

LAYER_VERDICT = {"PROVIDER": "ENV_BLOCKED", "ENV": "ENV_BLOCKED", "AGENT": "AGENT_FAILED", "SUT": "DEFECT_FOUND",
                 "TEST": "TEST_BROKEN", "HARNESS": "TEST_BROKEN", "UNKNOWN": "INCONCLUSIVE"}  # fmt: skip

classifications = st.lists(
    st.builds(Classification, unit=st.sampled_from(["test", "tool", "llm", "agent", "diff"]), layer=st.sampled_from(sorted(LAYER_VERDICT)),
              symptom=st.just("NONE"), matched_rule=st.sampled_from(["R3", "R5", "R10", "R11", "R12", None]), evidence=st.just("e")),
    max_size=8,
)  # fmt: skip


def expected_verdict(cs: list[Classification], flaky: bool, missed_possible: bool) -> str:
    present = [LAYER_VERDICT[c.layer] for c in cs]
    if present:
        return min(present, key=verdict_mod.ORDER.index)
    return "MISSED" if missed_possible else "FLAKY" if flaky else "PASS"


@given(cs=classifications, flaky=st.booleans(), missed_possible=st.booleans())
def test_the_highest_priority_verdict_present_wins(cs, flaky, missed_possible):
    outcome = verdict_mod.aggregate(cs, flaky=flaky, missed_possible=missed_possible)
    assert outcome.verdict == expected_verdict(cs, flaky, missed_possible)


@given(data=st.data(), cs=classifications, flaky=st.booleans(), missed_possible=st.booleans())
def test_the_order_of_observations_does_not_matter(data, cs, flaky, missed_possible):
    shuffled = data.draw(st.permutations(cs))
    a = verdict_mod.aggregate(cs, flaky=flaky, missed_possible=missed_possible)
    b = verdict_mod.aggregate(shuffled, flaky=flaky, missed_possible=missed_possible)
    assert (a.verdict, a.underlying_verdict) == (b.verdict, b.underlying_verdict)


# --------------------------------------------------------------------------- whole runs, from spans

def _span(sid: str, parent: str | None, name: str, attrs: dict | None = None, error: str | None = None) -> dict:
    events = [{"name": "exception", "attributes": {"exception.type": error, "exception.message": "boom"}}] if error else []
    return {"span_id": sid, "parent_span_id": parent, "name": name, "attributes": attrs or {}, "events": events,
            "status": {"code": "ERROR" if error else "OK", "message": "boom" if error else None}}  # fmt: skip


@st.composite
def runs_without_any_test(draw) -> list[dict]:
    """Pipeline-shaped traces in which no generated test was executed: the runners collected nothing or broke,
    or QA never got to a runner. A real pytest exit code 0 always comes with results, so it is not generated."""
    spans = [_span("r", None, "qa.run"), _span("q", "r", "agent.qa")]
    shape = draw(st.sampled_from(["runner_without_tests", "runner_raised", "no_runner"]))
    if shape == "no_runner":
        spans[1] = _span("q", "r", "agent.qa", error="HandoffError")
        return spans
    for i in range(draw(st.integers(1, 2))):
        tool = draw(st.sampled_from(["pytest", "playwright"]))
        if shape == "runner_raised":
            spans.append(_span(f"t{i}", "q", f"tool.{tool}", {"qa.tool.name": tool}, error=draw(st.sampled_from(["ToolTimeoutError", "PermissionDeniedError"]))))
        else:
            spans.append(_span(f"t{i}", "q", f"tool.{tool}", {"qa.tool.name": tool, "qa.tool.exit_code": draw(st.sampled_from([2, 3, 4, 5]))}))
    if draw(st.booleans()):  # the health probe after the runners
        spans.append(_span("h", "q", "tool.http_request", {"qa.tool.name": "http_request", "qa.http.route": "/health", "qa.http.status_code": 200}))
    return spans


@given(spans=runs_without_any_test())
def test_a_run_without_any_executed_test_is_never_pass(spans):
    outcome = verdict_mod.surface_outcome(observe(spans))
    assert outcome.verdict != "PASS", f"no test ran, yet the verdict is PASS: {[s['name'] for s in spans]}"


def _decision(i: int, kind: str) -> dict:
    bug, clean, decision, rule = {"detected": ("FAIL", "PASS", "DETECTED", "R11"), "broken": ("FAIL", "FAIL", "BROKEN", "R12"),
                                  "crash": ("ERROR", "PASS", "BROKEN", "R10"), "missed": ("PASS", "PASS", "NOT_DETECTED", None)}[kind]  # fmt: skip
    return {"node_id": f"generated/test_x.py::test_{i}", "bug_outcome": bug, "clean_outcome": clean, "decision": decision,
            "rule": rule, "symptom": None, "evidence": "e"}  # fmt: skip


@given(kinds=st.lists(st.sampled_from(["detected", "broken", "crash", "missed"]), min_size=1, max_size=6), at=st.integers(0, 6))
def test_one_more_test_passing_on_both_builds_keeps_defect_found(kinds, at):
    decisions = [_decision(i, k) for i, k in enumerate(kinds)]
    before = verdict_mod.final_outcome(observe([], differential={"status": "COMPLETE", "decisions": decisions}), bugs_enabled=True)
    assume(before.verdict == "DEFECT_FOUND")
    more = decisions[:at] + [_decision(99, "missed")] + decisions[at:]
    after = verdict_mod.final_outcome(observe([], differential={"status": "COMPLETE", "decisions": more}), bugs_enabled=True)
    assert after.verdict == "DEFECT_FOUND"
