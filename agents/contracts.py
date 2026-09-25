"""Input/output dataclasses passed between agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Surface = Literal["api", "ui"]
Verdict = Literal["PASS", "DEFECT_FOUND", "TEST_BROKEN", "AGENT_FAILED", "ENV_BLOCKED", "FLAKY"]


@dataclass(frozen=True)
class RequirementInput:
    requirement_id: str
    text: str


@dataclass(frozen=True)
class RequirementSpec:
    requirement_id: str
    summary: str
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True)
class TestCase:
    __test__ = False  # not a pytest test class

    id: str
    title: str
    surface: Surface
    steps: tuple[str, ...]
    expected: str


@dataclass(frozen=True)
class TestPlan:
    __test__ = False

    requirement_id: str
    cases: tuple[TestCase, ...]


@dataclass(frozen=True)
class GeneratedFile:
    path: str
    content: str
    surface: Surface


@dataclass(frozen=True)
class AutomationResult:
    requirement_id: str
    files: tuple[GeneratedFile, ...]


@dataclass(frozen=True)
class ToolExecution:
    tool: str
    ok: bool
    attempts: int
    exit_code: int | None = None
    summary: str = ""
    error: str | None = None  # set when the tool raised instead of returning a result
    data: dict[str, Any] = field(default_factory=dict)  # tool-specific details, e.g. junit counts


@dataclass(frozen=True)
class QAResult:
    requirement_id: str
    executions: tuple[ToolExecution, ...]


@dataclass(frozen=True)
class Report:
    requirement_id: str
    verdict: Verdict
    summary: str
