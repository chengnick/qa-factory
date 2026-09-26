from __future__ import annotations

import json
import re
from dataclasses import asdict

from agents.base import AgentDeps, AgentOutputError, HandoffError, ask_json, dict_list, field
from agents.contracts import AutomationResult, GeneratedFile, TestPlan
from tools.registry import ToolError

_FILENAME = re.compile(r"^generated/test_[a-z0-9_]+\.py$")

SYSTEM = """You are a test automation engineer. Turn the test plan into runnable pytest files.

Rules:
- Output JSON only: {"files": [{"path": "generated/test_<name>.py", "surface": "api"|"ui", "content": "<python source>"}]}
- Produce one file for the "api" cases and, only if the plan has "ui" cases, one file for the "ui" cases.
  Paths must match generated/test_[a-z0-9_]+.py and include the requirement id, e.g. generated/test_req005_api.py.
- These pytest fixtures already exist in generated/conftest.py. Use them; do NOT write a conftest,
  start servers, import application code, or hard-code URLs/ports:
    base_url            -> str, root URL of the running application
    as_user(username)   -> httpx.Client with base_url and the X-User header set (users: alice, bob, carol, dave)
    user_ids            -> dict username -> numeric user id
    new_project(owner="alice", members=())  -> int id of a brand-new project; members are added as project members
    page                -> Playwright sync Page (ui files only)
- as_user and new_project are factories: call them. Correct usage:
      def test_example(as_user, new_project, user_ids):
          alice = as_user("alice")
          pid = new_project(owner="alice", members=("bob",))
          r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "t"})
          assert r.status_code == 201, r.text
- UI tests: page.goto(f"{base_url}/?user=alice&project={pid}"), then
  expect(page.locator("body")).to_have_attribute("data-ready", "true") before interacting.
  Locate elements with page.get_by_test_id(...). Import expect from playwright.sync_api.
- Every test creates its own data and is independent of the others.
- Assert the exact status codes and fields the requirement specifies; include the response text in assertion
  messages, e.g. assert r.status_code == 409, r.text
- Allowed imports: pytest, httpx, uuid, re, playwright.sync_api."""


class AutomationAgent:
    name = "automation"

    def __init__(self, deps: AgentDeps, api_reference: str = "") -> None:
        self.deps = deps
        self.api_reference = api_reference

    def run(self, plan: TestPlan) -> AutomationResult:
        if not plan.cases:
            raise HandoffError("test_design", "test plan has no cases")
        user = f"Test plan for {plan.requirement_id}:\n{json.dumps(asdict(plan), ensure_ascii=False, indent=2)}"
        if self.api_reference:
            user += f"\n\nAPI reference:\n{self.api_reference}"
        data = ask_json(self.deps.llm, SYSTEM, user)
        files = []
        for raw in dict_list(data, "files"):
            path, surface = field(raw, "path", str), field(raw, "surface", str)
            if not _FILENAME.match(path):
                raise AgentOutputError(f"generated file path must match {_FILENAME.pattern}: {path!r}")
            if surface not in ("api", "ui"):
                raise AgentOutputError(f"file surface must be 'api' or 'ui', got {surface!r}")
            files.append(GeneratedFile(path, field(raw, "content", str), surface))
        if not files:
            raise AgentOutputError("no test files generated")
        if len({f.path for f in files}) != len(files):
            raise AgentOutputError("duplicate generated file paths")
        for f in files:
            result = self.deps.tools.call("file_write", path=f.path, content=f.content)
            if not result.ok:
                raise ToolError(f"file_write failed for {f.path}: {result.stdout}")
        return AutomationResult(plan.requirement_id, tuple(files))
