"""Property 1: whatever agent x tool x target is tried, a refused call never executes the tool and every security event
it leaves says executed: false. Tools are spies behind the real PermissionGate and TracedToolRegistry."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from permissions.policy import default_policy
from tests.property.prop_support import AGENTS, OTHER_RUN, SUT, SUT_ROUTES, TOOLS, gated_world, lookalike_routes, lookalike_urls
from tools.registry import PermissionDeniedError, UnknownToolError

WRITE_TARGETS = st.sampled_from([
    "generated/test_prop_a.py", "generated/sub/test_prop_b.py", "generated/conftest.py",
    "sut/app.py", "sut/new_module.py", "docs/spec.md", "benchmark/reference_tests/test_new.py",
    "benchmark/frozen.yaml", "traces/x/trace.json", f"../{OTHER_RUN}/meta.json", "artifacts/x.py", "../../outside.py",
    "README.md", "evaluation/run.py",
])  # fmt: skip
CONTENTS = st.sampled_from(["x = 1\n", "def test_a():\n    assert 1\n", "API_KEY = 'abcdef0123456789abcdef'\n"])


@st.composite
def generated_code(draw) -> str:
    """A generated test file: allowed, or breaking the generated-code policy in one of its ways."""
    return draw(st.sampled_from([
        "import pytest\n\n\ndef test_ok():\n    assert 1\n",
        "import os\n\n\ndef test_env():\n    assert os.environ\n",
        "def test_open():\n    open('x', 'w')\n",
        "def test_eval():\n    eval('1')\n",
        f"URL = '{draw(lookalike_urls())}'\n\n\ndef test_url():\n    assert URL\n",
        f"URL = '{SUT}/api/tasks'\n\n\ndef test_sut():\n    assert URL\n",
    ]))  # fmt: skip


@st.composite
def tool_calls(draw) -> tuple[str, dict, dict[str, str]]:
    """(tool, args, files to create in the workspace first) for every registered tool."""
    tool = draw(st.sampled_from(TOOLS))
    if tool == "file_write":
        return tool, {"path": draw(WRITE_TARGETS), "content": draw(CONTENTS)}, {}
    if tool == "http_request":
        route = draw(SUT_ROUTES | lookalike_routes())
        return tool, {"method": draw(st.sampled_from(["GET", "POST"])), "route": route}, {}
    name = f"generated/test_prop_{draw(st.integers(0, 3))}.py"
    return tool, {"paths": [name]}, {name: draw(generated_code())}


@given(agent=st.sampled_from(AGENTS), call=tool_calls())
def test_a_refused_call_never_executes_and_records_only_unexecuted_events(agent, call):
    tool, args, files = call
    with gated_world() as w:
        for rel, source in files.items():
            (w.workspace / rel).write_text(source, encoding="utf-8")
        try:
            w.traced.call_as(agent, tool, args)
            refused = False
        except (PermissionDeniedError, UnknownToolError):
            refused = True
        events = w.recorder.events
        if refused:
            assert w.executions == 0, f"refused {agent} {tool} {args} but the tool ran {w.executions} time(s)"
            assert events, "a refusal must leave a security event"
        else:
            assert w.executions == 1
        assert all(e.executed is False for e in events), [e for e in events if e.executed]
        if default_policy().tool_rule(agent, tool) is None:  # the permission table alone already forbids it
            assert refused and w.executions == 0
