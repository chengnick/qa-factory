"""Wires the five agents together and mounts instrumentation around them.

This is the only place where agents meet observability; agents/ never imports it.
The verdict is decided at the end of the run by classification/ from the run's own trace
(spec v3 §5): a surface verdict from the pipeline alone and, in evaluation mode, a cross-validated one.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.automation import AutomationAgent
from agents.base import AgentDeps
from agents.contracts import AutomationResult, QAResult, Report, RequirementInput, RevisionRequest
from agents.qa import QAAgent
from agents.report import ReportAgent
from agents.requirement import RequirementAgent
from agents.test_design import TestDesignAgent
from agents.version import PROMPT_VERSION
from classification.observations import observe
from classification.verdict import Outcome, final_outcome, surface_outcome
from llm.client import LLMClient
from observability.instrument import AgentTools, Instrumentation, RunHandle, TracedLLM, TracedToolRegistry, traced_agent, traced_run
from observability.json_exporter import span_to_dict
from permissions.gate import PermissionGate
from permissions.policy import Policy, default_policy
from security.events import SecurityRecorder
from tools.registry import NO_RETRY, RetryPolicy, ToolRegistry
from tools.workspace import snapshot_round


@dataclass(frozen=True)
class PipelineResult:
    trace_id: str
    verdict: str  # final: cross-validated when a differential ran, otherwise the surface verdict
    report: Report | None
    error: str | None = None
    surface_verdict: str | None = None  # what the pipeline alone can say (unverified)
    differential: Any = None  # evaluation.differential.DifferentialResult when evaluation mode ran
    underlying_verdict: str | None = None  # set when verdict is FLAKY
    classification: dict[str, Any] | None = None  # {"surface": Outcome json, "final": Outcome json | None}
    security: dict[str, Any] | None = None  # security_events.json content: {"run_id", "breach", "events"}
    policy: dict[str, Any] | None = None  # {"hash", "path", "permission_checks", "allowed", "denied"}
    rounds: list[dict[str, Any]] = dataclasses.field(default_factory=list)  # rounds.json: files and test results per round


# Evaluation hook: given the final generated tests, cross-validate them (evaluation/differential.py).
Differential = Callable[[AutomationResult], Any]


def run_pipeline(
    requirement: RequirementInput,
    *,
    llm: LLMClient,
    tools: ToolRegistry,
    inst: Instrumentation,
    sut_bugs: Sequence[str] = (),
    llm_retry: RetryPolicy = NO_RETRY,
    api_reference: str = "",
    run_id: str | None = None,
    dataset: str | None = None,
    differential: Differential | None = None,
    workspace: Path | None = None,
    sut_url: str | None = None,
    agents: Mapping[str, Callable[[AgentDeps], Any]] | None = None,
    policy: Policy | None = None,
    max_rounds: int = 1,
) -> PipelineResult:
    """`agents` replaces individual agents by name (test doubles such as testing.fake_agent.ScriptedAgent);
    a replacement receives that agent's own gated deps, so the permission table still applies to it.

    Rounds (spec v3 §9): round 1 is automation + QA. While round N had a failing test, fewer than `max_rounds`
    rounds ran and the automation agent declares `revises = True`, round N+1 hands it a RevisionRequest and
    runs QA again. The real AutomationAgent does not revise, so live runs have exactly one round. Each round's
    tests are snapshotted to generated/roundN/ (when a workspace is given) and listed in `rounds`."""
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    if inst.collector is None:
        raise ValueError("Instrumentation needs a span collector (observability.setup.new_instrumentation) to classify the run")
    security = SecurityRecorder(run_id)
    inst = dataclasses.replace(inst, security=security)
    policy = policy or default_policy()
    gate = PermissionGate(security, registered=tools.names, workspace=workspace, sut_url=sut_url, policy=policy)
    traced_tools = TracedToolRegistry(tools, inst, guard=gate.check)
    traced_llm = TracedLLM(llm, inst, llm_retry)

    def deps(agent: str) -> AgentDeps:  # each agent calls tools as itself, so the gate applies its row of §8.1
        return AgentDeps(llm=traced_llm, tools=AgentTools(traced_tools, agent))

    factories: dict[str, Callable[[AgentDeps], Any]] = {
        "requirement": RequirementAgent,
        "test_design": lambda d: TestDesignAgent(d, api_reference),
        "automation": lambda d: AutomationAgent(d, api_reference),
        "qa": QAAgent,
        "report": ReportAgent,
        **(agents or {}),
    }
    requirement_agent, design_agent, automation_agent, qa_agent, report_agent = (
        traced_agent(factories[name](deps(name)), inst) for name in ("requirement", "test_design", "automation", "qa", "report")
    )
    with traced_run(inst, requirement.requirement_id, sut_bugs, run_id=run_id, prompt_version=PROMPT_VERSION, dataset=dataset) as run:
        report: Report | None = None
        error: str | None = None
        diff = None
        rounds: list[dict[str, Any]] = []
        try:
            plan = design_agent.run(requirement_agent.run(requirement))
            revises = bool(getattr(automation_agent.inner, "revises", False))
            request: Any = plan
            while True:
                n = len(rounds) + 1
                traced_tools.round = n
                automation = automation_agent.run(request, {"qa.test.round": n})
                rounds.append(_start_round(n, automation, workspace))
                qa = qa_agent.run(automation, {"qa.test.round": n})
                rounds[-1]["results"] = _round_results(qa)
                if n >= max_rounds or not revises or not _has_failures(rounds[-1]["results"]):
                    break
                request = RevisionRequest(plan, automation, qa, n + 1)
            traced_tools.round = None
            report = report_agent.run(qa)
        except Exception as exc:  # classified from the trace below; an unmatched exception becomes UNKNOWN
            run.fail(exc)
            error = f"{type(exc).__name__}: {exc}"
        else:
            if differential is not None:
                diff = differential(automation)
        run.set_attribute("qa.policy.hash", policy.hash)
        run.set_attribute("qa.policy.path", policy.display_path)
        result = _conclude(run, inst, report, error, diff, security, bugs_enabled=bool(sut_bugs))
        return dataclasses.replace(result, policy={"hash": policy.hash, "path": policy.display_path, **gate.stats}, rounds=rounds)


def _start_round(n: int, automation: AutomationResult, workspace: Path | None) -> dict[str, Any]:
    files = [(f.path, f.content) for f in automation.files]
    if workspace is not None:
        saved = snapshot_round(workspace, n, files)
    else:  # fake tools without a workspace: nothing on disk, keep the hashes only
        saved = [{"path": p, "snapshot": None, "sha256": hashlib.sha256(c.encode("utf-8")).hexdigest()} for p, c in files]
    return {"round": n, "files": saved, "results": []}


def _round_results(qa: QAResult) -> list[dict[str, Any]]:
    """Per-test outcomes of one round, as the runners reported them (node_id, outcome, message, tool)."""
    return [{**r, "tool": e.tool} for e in qa.executions for r in e.data.get("results", ())]


def _has_failures(results: list[dict[str, Any]]) -> bool:
    return any(r["outcome"] in ("FAIL", "ERROR") for r in results)


def _conclude(
    run: RunHandle, inst: Instrumentation, report: Report | None, error: str | None, diff: Any, security: SecurityRecorder, *, bugs_enabled: bool
) -> PipelineResult:
    spans = [span_to_dict(s) for s in inst.collector.spans(run.trace_id)]
    obs = observe(spans, differential=diff.to_json() if diff is not None else None)
    surface = surface_outcome(obs)
    final = final_outcome(obs, bugs_enabled=bugs_enabled) if diff is not None else surface
    _annotate_root(run, final, surface)
    run.set_attribute("qa.security.events", len(security.events))
    run.set_attribute("qa.security.breach", security.breach)
    classification = {"surface": surface.to_json(), "final": final.to_json() if diff is not None else None}
    return PipelineResult(
        run.trace_id, final.verdict, report, error, surface.verdict, diff, final.underlying_verdict, classification, security.to_json()
    )  # fmt: skip


def _annotate_root(run: RunHandle, final: Outcome, surface: Outcome) -> None:
    run.set_verdict(final.verdict)
    run.set_attribute("qa.verdict.surface", surface.verdict)
    if final.underlying_verdict:
        run.set_attribute("qa.verdict.underlying", final.underlying_verdict)
    counts = final.counts
    run.set_attribute("qa.classification.total", counts["total"])
    run.set_attribute("qa.classification.unknown", counts["unknown"])
    if c := final.decided_by:
        run.set_attribute("qa.failure.layer", c.layer)
        run.set_attribute("qa.failure.symptom", c.symptom)
        run.set_attribute("qa.failure.rule", c.matched_rule or "UNKNOWN")
