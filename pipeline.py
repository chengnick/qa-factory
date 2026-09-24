"""Wires the five agents together and mounts instrumentation around them.

This is the only place where agents meet observability; agents/ never imports it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agents.automation import AutomationAgent
from agents.base import AgentDeps
from agents.contracts import QAResult, Report, RequirementInput
from agents.qa import QAAgent
from agents.report import ReportAgent, provisional_verdict
from agents.requirement import RequirementAgent
from agents.test_design import TestDesignAgent
from llm.client import LLMClient
from observability.instrument import Instrumentation, TracedLLM, TracedToolRegistry, traced_agent, traced_run
from tools.registry import NO_RETRY, RetryPolicy, ToolRegistry


@dataclass(frozen=True)
class PipelineResult:
    trace_id: str
    verdict: str
    report: Report | None
    error: str | None = None


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
) -> PipelineResult:
    deps = AgentDeps(llm=TracedLLM(llm, inst, llm_retry), tools=TracedToolRegistry(tools, inst))
    stages = [
        traced_agent(RequirementAgent(deps), inst),
        traced_agent(TestDesignAgent(deps), inst),
        traced_agent(AutomationAgent(deps), inst),
        traced_agent(QAAgent(deps), inst, _qa_attributes),
        traced_agent(ReportAgent(deps), inst),
    ]
    with traced_run(inst, requirement.requirement_id, sut_bugs) as run:
        data: object = requirement
        try:
            for stage in stages:
                data = stage.run(data)
        except Exception as exc:  # any agent failure ends the run with a verdict, never a bare crash
            run.set_verdict("AGENT_FAILED")
            run.fail(exc)
            return PipelineResult(run.trace_id, "AGENT_FAILED", None, f"{type(exc).__name__}: {exc}")
        assert isinstance(data, Report)
        run.set_verdict(data.verdict)
        return PipelineResult(run.trace_id, data.verdict, data)
