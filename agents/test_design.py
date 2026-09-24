from __future__ import annotations

import json
from dataclasses import asdict

from agents.base import AgentDeps, AgentOutputError, ask_json, dict_list, field, str_list
from agents.contracts import RequirementSpec, TestCase, TestPlan

SYSTEM = (
    "You are a test designer. Design test cases for the requirement. Answer with JSON only: "
    '{"cases": [{"id": str, "title": str, "surface": "api"|"ui", "steps": [str], "expected": str}]}'
)


class TestDesignAgent:
    __test__ = False
    name = "test_design"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, spec: RequirementSpec) -> TestPlan:
        data = ask_json(self.deps.llm, SYSTEM, json.dumps(asdict(spec), ensure_ascii=False))
        cases = []
        for raw in dict_list(data, "cases"):
            surface = field(raw, "surface", str)
            if surface not in ("api", "ui"):
                raise AgentOutputError(f"case surface must be 'api' or 'ui', got {surface!r}")
            cases.append(
                TestCase(field(raw, "id", str), field(raw, "title", str), surface, str_list(raw, "steps"), field(raw, "expected", str))
            )
        if not cases:
            raise AgentOutputError("test plan has no cases")
        return TestPlan(spec.requirement_id, tuple(cases))
