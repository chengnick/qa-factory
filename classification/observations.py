"""Turn a trace (span dicts, spec v2 §3.4 format) into classification units.

A unit is one thing that went wrong and should get exactly one (layer, symptom) classification:

    health   the SUT health check failed (QA probe or an evaluation build)
    llm      an llm.chat call failed after its retries
    tool     a tool call failed as a whole (exception, or a runner exit code other than 0/1)
    agent    an agent failed on its own (bad LLM output, rejected handoff), not because a child failed
    test     one generated test failed in the pipeline's QA run (surface mode only)
    diff     one cross-validation decision other than NOT_DETECTED / PASS (evaluation mode only)
    status   cross-validation ended in a state no rule covers (e.g. test files changed)

Failed attempts followed by a successful attempt are not units; they only mark the run FLAKY.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

RUNNERS = ("pytest", "playwright")
EVALUATION_SPANS = ("evaluation.differential", "evaluation.build")


@dataclass(frozen=True)
class Unit:
    kind: str
    span_id: str | None = None
    span_name: str = ""
    agent: str | None = None
    exception: str | None = None
    message: str = ""
    tool: str | None = None
    exit_code: int | None = None
    route: str | None = None
    status_code: int | None = None
    test_id: str | None = None
    outcome: str | None = None
    collection_error: bool = False
    health_ok: bool | None = None
    decision_rule: str | None = None
    upstream: str | None = None


@dataclass
class Observations:
    surface: list[Unit] = field(default_factory=list)  # units for the unverified (pipeline-only) verdict
    evaluation: list[Unit] = field(default_factory=list)  # units that replace QA test units when cross-validated
    flaky: bool = False
    flaky_evidence: list[str] = field(default_factory=list)
    differential: dict[str, Any] | None = None


def _exception(span: dict[str, Any]) -> tuple[str | None, str, str | None]:
    for event in span.get("events", []):
        if event["name"] == "exception":
            attrs = event["attributes"]
            return attrs.get("exception.type"), attrs.get("exception.message", ""), attrs.get("exception.upstream")
    return None, (span.get("status") or {}).get("message") or "", None


def _is_error(span: dict[str, Any]) -> bool:
    return (span.get("status") or {}).get("code") == "ERROR"


def _test_results(span: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"node_id": e["attributes"]["qa.test.id"], "outcome": e["attributes"]["qa.test.outcome"], "message": e["attributes"].get("qa.test.message", "")}
        for e in span.get("events", [])
        if e["name"] == "qa.test.result"
    ]


def observe(
    spans: Iterable[dict[str, Any]],
    differential: dict[str, Any] | None = None,
    test_results_fallback: dict[str, list[dict[str, str]]] | None = None,
) -> Observations:
    """`test_results_fallback` maps a tool span_id to its per-test results, for traces written before
    tool spans carried qa.test.result events (Phase 2R); taken from the run's junit reports."""
    spans = list(spans)
    by_id = {s["span_id"]: s for s in spans}
    children: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        children[s.get("parent_span_id")].append(s)

    def ancestors(span: dict[str, Any]) -> Iterable[dict[str, Any]]:
        parent = by_id.get(span.get("parent_span_id"))
        while parent is not None:
            yield parent
            parent = by_id.get(parent.get("parent_span_id"))

    def agent_of(span: dict[str, Any]) -> str | None:
        for a in [span, *ancestors(span)]:
            if a["name"].startswith("agent."):
                return a["name"].removeprefix("agent.")
        return None

    def in_evaluation(span: dict[str, Any]) -> bool:
        return any(a["name"] in EVALUATION_SPANS for a in [span, *ancestors(span)])

    def has_error_descendant(span: dict[str, Any]) -> bool:
        return any(_is_error(c) or has_error_descendant(c) for c in children[span["span_id"]])

    obs = Observations(differential=differential)
    fallback = test_results_fallback or {}

    # Run-level health: the QA probe (pipeline) - used by R14 / R15.
    probes = [s for s in spans if s["name"] == "tool.http_request" and s["attributes"].get("qa.http.route") == "/health" and not in_evaluation(s)]
    health_ok = None if not probes else all(not _is_error(p) and p["attributes"].get("qa.http.status_code") == 200 for p in probes)

    # Revision rounds (Phase 4): the verdict is about the tests the run ended with; how earlier rounds were changed
    # is judged by the Workflow Evaluator (evaluation/workflow.py), so superseded rounds' test runs are skipped here.
    last_round = max((s["attributes"].get("qa.test.round", 0) for s in spans if s["name"].startswith("tool.")), default=0)

    for span in spans:
        name, attrs = span["name"], span["attributes"]
        evaluation = in_evaluation(span)

        # Retried-away failures: an attempt failed, a later sibling attempt succeeded.
        if name == "attempt" and _is_error(span):
            siblings = [c for c in children[span.get("parent_span_id")] if c["name"] == "attempt"]
            later_ok = [c for c in siblings if c["attributes"].get("qa.retry.attempt", 0) > attrs.get("qa.retry.attempt", 0) and not _is_error(c)]
            if later_ok:
                obs.flaky = True
                parent = by_id.get(span.get("parent_span_id"), {})
                obs.flaky_evidence.append(f"{parent.get('name', '?')} attempt {attrs.get('qa.retry.attempt')} failed, a later attempt passed")
            continue

        if name == "evaluation.build" and attrs.get("qa.failure.rule") == "R1":
            _, message, _ = _exception(span)
            message = (span.get("status") or {}).get("message") or message
            obs.evaluation.append(Unit("health", span["span_id"], name, message=message, route="/health"))
            continue

        if name == "llm.chat" and _is_error(span):
            exc, message, _ = _exception(span)
            obs.surface.append(Unit("llm", span["span_id"], name, agent_of(span), exc, message))
            continue

        if name.startswith("tool."):
            tool = attrs.get("qa.tool.name") or name.removeprefix("tool.")
            exc, message, _ = _exception(span)
            if tool == "http_request" and attrs.get("qa.http.route") == "/health":
                if _is_error(span) and not evaluation:  # evaluation builds report R1 on the build span
                    obs.surface.append(
                        Unit("health", span["span_id"], name, agent_of(span), exc, message, tool, route="/health", status_code=attrs.get("qa.http.status_code"))
                    )
                continue
            exit_code = attrs.get("qa.tool.exit_code")
            if tool in RUNNERS and attrs.get("qa.test.round", last_round) < last_round:
                continue
            if tool in RUNNERS and exc is None:
                results = _test_results(span) or fallback.get(span["span_id"], [])
                collection = attrs.get("qa.test.collection_errors", 0) > 0 or any("::" not in r["node_id"] and r["outcome"] == "ERROR" for r in results)
                if exit_code in (0, None) and not collection:
                    continue
                if exit_code == 1 and not collection and results:
                    if not evaluation:  # per-test units (the evaluation builds are judged by the differential)
                        for r in results:
                            if r["outcome"] in ("FAIL", "ERROR"):
                                obs.surface.append(
                                    Unit("test", span["span_id"], name, agent_of(span), tool=tool, exit_code=1, test_id=r["node_id"],
                                         outcome=r["outcome"], message=r["message"], health_ok=health_ok)  # fmt: skip
                                )
                    continue
                if evaluation:
                    continue  # a build's runner exit code is summarised by the differential status
                obs.surface.append(Unit("tool", span["span_id"], name, agent_of(span), None, message, tool, exit_code, collection_error=collection))
                continue
            if _is_error(span):
                unit = Unit("tool", span["span_id"], name, agent_of(span), exc, message, tool, exit_code,
                            route=attrs.get("qa.http.route"), status_code=attrs.get("qa.http.status_code"))  # fmt: skip
                (obs.evaluation if evaluation else obs.surface).append(unit)
            continue

        if name.startswith("agent.") and _is_error(span) and not has_error_descendant(span):
            exc, message, upstream = _exception(span)
            obs.surface.append(Unit("agent", span["span_id"], name, agent_of(span), exc, message, upstream=upstream))

    if differential is not None:
        status = differential.get("status")
        if status == "COMPLETE":
            for d in differential.get("decisions", []):
                if d["decision"] in ("NOT_DETECTED", "PASS"):
                    continue
                message = d.get("evidence", "")
                obs.evaluation.append(
                    Unit("diff", test_id=d["node_id"], outcome=d["bug_outcome"], message=message, decision_rule=d["rule"], health_ok=True)
                )
        elif status == "TAMPERED":
            obs.evaluation.append(Unit("status", message=differential.get("reason") or status))
    return obs
