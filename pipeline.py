"""Wires the five agents together and mounts instrumentation around them.

This is the only place where agents meet observability; agents/ never imports it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agents.automation import AutomationAgent
from agents.base import AgentDeps
from agents.contracts import AutomationResult, QAResult, Report, RequirementInput
from agents.qa import QAAgent
from agents.report import ReportAgent, exception_verdict, provisional_verdict
from agents.requirement import RequirementAgent
from agents.test_design import TestDesignAgent
from agents.version import PROMPT_VERSION
from llm.client import LLMClient
from observability.instrument import Instrumentation, TracedLLM, TracedToolRegistry, traced_agent, traced_run
from tools.registry import NO_RETRY, RetryPolicy, ToolRegistry


@dataclass(frozen=True)
class PipelineResult:
    trace_id: str
    verdict: str  # final: cross-validated when a differential ran, otherwise the surface verdict
    report: Report | None
    error: str | None = None
    surface_verdict: str | None = None  # the pipeline's own (unverified) verdict
    differential: Any = None  # evaluation.differential.DifferentialResult when evaluation mode ran


# Evaluation hook: given the final generated tests, cross-validate them (evaluation/differential.py).
Differential = Callable[[AutomationResult], Any]


def _qa_attributes(result: QAResult) -> dict[str, str]:
    return {"qa.verdict": provisional_verdict(result)}


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
) -> PipelineResult:
    deps = AgentDeps(llm=TracedLLM(llm, inst, llm_retry), tools=TracedToolRegistry(tools, inst))
    requirement_agent = traced_agent(RequirementAgent(deps), inst)
    design_agent = traced_agent(TestDesignAgent(deps, api_reference), inst)
    automation_agent = traced_agent(AutomationAgent(deps, api_reference), inst)
    qa_agent = traced_agent(QAAgent(deps), inst, _qa_attributes)
    report_agent = traced_agent(ReportAgent(deps), inst)
    with traced_run(inst, requirement.requirement_id, sut_bugs, run_id=run_id, prompt_version=PROMPT_VERSION, dataset=dataset) as run:
        try:
            automation = automation_agent.run(design_agent.run(requirement_agent.run(requirement)))
            report = report_agent.run(qa_agent.run(automation))
        except Exception as exc:
            verdict = exception_verdict(exc)
            if verdict is None:
                raise  # unclassified exception: a bug in our code, not a verdict about the SUT (root span marked ERROR)
            run.set_verdict(verdict)
            run.fail(exc)
            return PipelineResult(run.trace_id, verdict, None, f"{type(exc).__name__}: {exc}", surface_verdict=verdict)
        run.set_attribute("qa.verdict.surface", report.verdict)
        if differential is None:
            run.set_verdict(report.verdict)
            return PipelineResult(run.trace_id, report.verdict, report, surface_verdict=report.verdict)
        diff = differential(automation)
        run.set_verdict(diff.verdict)
        return PipelineResult(run.trace_id, diff.verdict, report, surface_verdict=report.verdict, differential=diff)
