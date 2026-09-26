"""ScriptedAgent: an agent whose tool calls come from a script, not from code paths an LLM can reach.

In this pipeline tool routing is fixed: agents decide which tool to call, the LLM only produces content.
So misuse such as calling an unregistered tool, passing wrong arguments, repeating a failing call or
writing outside generated/ cannot come from the LLM; ScriptedAgent stands in for "an agent that did it"
to test the safeguards (gate, registry, trace, classifier), not the model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from agents.base import AgentDeps


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    swallow: bool = False  # catch the error and carry on with the script (to try several actions in one run)


class ScriptedAgent:
    def __init__(self, name: str, deps: AgentDeps, calls: Sequence[ToolCall] = (), output: Callable[[Any], Any] | Any = None) -> None:
        self.name = name
        self.deps = deps
        self.calls = list(calls)
        self._output = output
        self.errors: list[str] = []

    def run(self, inp: Any) -> Any:
        for call in self.calls:
            try:
                self.deps.tools.call(call.tool, **call.args)
            except Exception as exc:
                if not call.swallow:
                    raise
                self.errors.append(f"{type(exc).__name__}: {exc}")
        return self._output(inp) if callable(self._output) else self._output


def scripted(name: str, calls: Sequence[ToolCall] = (), output: Callable[[Any], Any] | Any = None) -> Callable[[AgentDeps], ScriptedAgent]:
    """Factory for run_pipeline(agents={...}): the pipeline supplies the agent's own (gated) deps."""
    return lambda deps: ScriptedAgent(name, deps, calls, output)
