from __future__ import annotations

from agents.base import AgentDeps, AgentOutputError, ask_json, field, str_list
from agents.contracts import RequirementInput, RequirementSpec

SYSTEM = (
    "You are a QA analyst. Read the requirement and answer with JSON only: "
    '{"summary": str, "acceptance_criteria": [str, ...]}'
)


class RequirementAgent:
    name = "requirement"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, inp: RequirementInput) -> RequirementSpec:
        data = ask_json(self.deps.llm, SYSTEM, f"Requirement {inp.requirement_id}:\n\n{inp.text}")
        criteria = str_list(data, "acceptance_criteria")
        if not criteria:
            raise AgentOutputError("acceptance_criteria must not be empty")
        return RequirementSpec(inp.requirement_id, field(data, "summary", str), criteria)
