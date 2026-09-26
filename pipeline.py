"""Wires the five agents together and mounts instrumentation around them.

This is the only place where agents meet observability; agents/ never imports it.
The verdict is decided at the end of the run by classification/ from the run's own trace
(spec v3 §5): a surface verdict from the pipeline alone and, in evaluation mode, a cross-validated one.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.automation import AutomationAgent
from agents.base import AgentDeps
from agents.contracts import AutomationResult, Report, RequirementInput
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
from security.events import SecurityRecorder
from tools.registry import NO_RETRY, RetryPolicy, ToolRegistry


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
) -> PipelineResult:
    if inst.collector is None:
        raise ValueError("Instrumentation needs a span collector (observability.setup.new_instrumentation) to classify the run")
    security = SecurityRecorder(run_id)
    inst = dataclasses.replace(inst, security=security)
    gate = PermissionGate(security, registered=tools.names, workspace=workspace, sut_url=sut_url)
    traced_tools = TracedToolRegistry(tools, inst, guard=gate.check)
    traced_llm = TracedLLM(llm, inst, llm_retry)

    def deps(agent: str) -> AgentDeps:  # each agent calls tools as itself, so the gate applies its row of §8.1
        return AgentDeps(llm=traced_llm, tools=AgentTools(traced_tools, agent))

    requirement_agent = traced_agent(RequirementAgent(deps("requirement")), inst)
    design_agent = traced_agent(TestDesignAgent(deps("test_design"), api_reference), inst)
    automation_agent = traced_agent(AutomationAgent(deps("automation"), api_reference), inst)
    qa_agent = traced_agent(QAAgent(deps("qa")), inst)
    report_agent = traced_agent(ReportAgent(deps("report")), inst)
    with traced_run(inst, requirement.requirement_id, sut_bugs, run_id=run_id, prompt_version=PROMPT_VERSION, dataset=dataset) as run:
        report: Report | None = None
        error: str | None = None
        diff = None
        try:
            automation = automation_agent.run(design_agent.run(requirement_agent.run(requirement)))
            report = report_agent.run(qa_agent.run(automation))
        except Exception as exc:  # classified from the trace below; an unmatched exception becomes UNKNOWN
            run.fail(exc)
            error = f"{type(exc).__name__}: {exc}"
        else:
            if differential is not None:
                diff = differential(automation)
        return _conclude(run, inst, report, error, diff, security, bugs_enabled=bool(sut_bugs))


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
