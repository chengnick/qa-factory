from __future__ import annotations

import json
from dataclasses import asdict

from agents.base import AgentDeps, AgentOutputError, HandoffError, ask_json, dict_list, field, str_list
from agents.contracts import RequirementSpec, TestCase, TestPlan

MAX_CASES = 8
SYSTEM = f"""You are a senior QA engineer designing black-box tests for one requirement of a web application.

Design 2 to {MAX_CASES} test cases that together verify every acceptance criterion, with emphasis on
boundaries, forbidden transitions, and permission rules. Test only behaviour the requirement states.
Each case is either "api" (HTTP calls only) or "ui" (drives the web page in a browser); prefer "api"
unless the criterion is about what the page shows.

Rules:
- Every expected result must follow from a sentence in the requirement; quote that criterion in "expected".
- When steps act on the same entity in sequence, track its current state after each step and derive each
  step's expected result from the requirement for that state. Prefer a fresh entity per check.
- When a rule covers a small enumerable set (e.g. "any transition from a state", every status, every role,
  both sides of a boundary), check each member explicitly instead of sampling one.

Answer with JSON only:
{{"cases": [{{"id": "TC-1", "title": str, "surface": "api"|"ui", "steps": [str], "expected": str}}]}}"""


class TestDesignAgent:
    __test__ = False
    name = "test_design"

    def __init__(self, deps: AgentDeps, api_reference: str = "") -> None:
        self.deps = deps
        self.api_reference = api_reference

    def run(self, spec: RequirementSpec) -> TestPlan:
        if not spec.acceptance_criteria or not all(c.strip() for c in spec.acceptance_criteria):
            raise HandoffError("requirement", "acceptance_criteria missing or blank")
        user = f"Requirement:\n{json.dumps(asdict(spec), ensure_ascii=False, indent=2)}"
        if self.api_reference:
            user += f"\n\nAPI reference:\n{self.api_reference}"
        data = ask_json(self.deps.llm, SYSTEM, user)
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
        if len(cases) > MAX_CASES:
            raise AgentOutputError(f"test plan has {len(cases)} cases; at most {MAX_CASES} allowed")
        return TestPlan(spec.requirement_id, tuple(cases))
