from __future__ import annotations

import json
from dataclasses import asdict

from agents.base import AgentDeps, AgentOutputError, ask_json, dict_list, field
from agents.contracts import AutomationResult, GeneratedFile, TestPlan
from tools.registry import ToolError

GENERATED_DIR = "generated/"
SYSTEM = (
    "You are a test automation engineer. Write pytest files for the test plan. Answer with JSON only: "
    '{"files": [{"path": "generated/<name>.py", "surface": "api"|"ui", "content": str}]}'
)


class AutomationAgent:
    name = "automation"

    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def run(self, plan: TestPlan) -> AutomationResult:
        data = ask_json(self.deps.llm, SYSTEM, json.dumps(asdict(plan), ensure_ascii=False))
        files = []
        for raw in dict_list(data, "files"):
            path, surface = field(raw, "path", str), field(raw, "surface", str)
            if not path.startswith(GENERATED_DIR) or ".." in path:
                raise AgentOutputError(f"generated file must live under {GENERATED_DIR}: {path!r}")
            if surface not in ("api", "ui"):
                raise AgentOutputError(f"file surface must be 'api' or 'ui', got {surface!r}")
            files.append(GeneratedFile(path, field(raw, "content", str), surface))
        if not files:
            raise AgentOutputError("no test files generated")
        for f in files:
            result = self.deps.tools.call("file_write", path=f.path, content=f.content)
            if not result.ok:
                raise ToolError(f"file_write failed for {f.path}: {result.stdout}")
        return AutomationResult(plan.requirement_id, tuple(files))
