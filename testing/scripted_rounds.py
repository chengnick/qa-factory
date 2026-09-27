"""ScriptedRounds (spec v3 §10.1): an automation agent that revises its tests over several rounds from a script.

The real AutomationAgent never revises (Phase 4 has no LLM-driven revision loop). ScriptedRounds stands in for
"an agent that changed its tests between rounds", so the Workflow Evaluator's W01-W03 can be shown to fire
(and not to fire) on known histories. It writes every file through file_write, so the gate still applies.

`runner_result` scripts the matching per-round pytest outcome for a FakeTool.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from agents.base import AgentDeps
from agents.contracts import AutomationResult, GeneratedFile, RevisionRequest, TestPlan
from tools.registry import ToolError, ToolResult

API = "generated/test_req005_api.py"


class ScriptedRounds:
    name = "automation"
    revises = True

    def __init__(self, deps: AgentDeps, rounds: Sequence[Mapping[str, str]], requirement_id: str = "REQ-005") -> None:
        if not rounds:
            raise ValueError("ScriptedRounds needs at least one round")
        self.deps = deps
        self.rounds = list(rounds)
        self.requirement_id = requirement_id
        self.requests: list[TestPlan | RevisionRequest] = []

    def run(self, request: TestPlan | RevisionRequest) -> AutomationResult:
        self.requests.append(request)
        n = request.round if isinstance(request, RevisionRequest) else 1
        files = self.rounds[min(n, len(self.rounds)) - 1]
        for path, content in files.items():
            result = self.deps.tools.call("file_write", path=path, content=content)
            if not result.ok:
                raise ToolError(f"file_write failed for {path}: {result.stdout}")
        return AutomationResult(self.requirement_id, tuple(GeneratedFile(p, c, "api") for p, c in files.items()))


def scripted_rounds(rounds: Sequence[Mapping[str, str]]) -> Callable[[AgentDeps], ScriptedRounds]:
    """Factory for run_pipeline(agents={"automation": ...})."""
    return lambda deps: ScriptedRounds(deps, rounds)


def runner_result(outcomes: Mapping[str, tuple[str, str]]) -> ToolResult:
    """{node_id: (outcome, message)} -> the ToolResult a pytest run with those outcomes returns."""
    failed = sum(1 for o, _ in outcomes.values() if o != "PASS")
    results = [{"node_id": n, "outcome": o, "message": m} for n, (o, m) in outcomes.items()]
    summary = f"{failed} failed, {len(outcomes) - failed} passed" if failed else f"{len(outcomes)} passed"
    return ToolResult(ok=not failed, exit_code=1 if failed else 0, stdout=summary, command="pytest", data={"results": results})


# --------------------------------------------------------------------------- canned histories (REQ-005)

STRICT = '''def test_done_is_terminal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "t"}).json()["id"]
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "invalid_transition", r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"
'''

WEAKENED = '''def test_done_is_terminal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "t"}).json()["id"]
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r is not None
'''

REWRITTEN = STRICT.replace("assert r.status_code == 409, r.text", "assert r.status_code == 200, r.text").replace(
    '    assert r.json()["error"] == "invalid_transition", r.text\n    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"\n',
    '    assert r.json()["status"] == "in_progress", r.text\n    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "in_progress"\n',
)

# A legitimate fix: the setup was wrong (the task never reached "done"), the assertions stay.
FIXED_SETUP = STRICT.replace(
    '    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})\n',
    '    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})\n    assert r.status_code == 200, r.text\n',
)

OTHER = '''def test_task_starts_todo(as_user, new_project):
    pid = new_project()
    r = as_user("alice").post(f"/api/projects/{pid}/tasks", json={"title": "t"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "todo", r.text
'''

NODE = f"{API}::test_done_is_terminal"
OTHER_NODE = f"{API}::test_task_starts_todo"
BUG_MESSAGE = "AssertionError: {\"id\": 7, \"status\": \"in_progress\"}\nassert 200 == 409\n +  where 200 = <Response [200 OK]>.status_code"
