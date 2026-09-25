"""Parameter schema validation: a bad call is rejected before the tool runs."""

import pytest
from opentelemetry.trace import StatusCode

from observability.instrument import TracedToolRegistry
from testing.fake_tool import FakeTool
from tools.registry import Param, ToolArgumentError, ToolRegistry, ToolResult

OK = ToolResult(ok=True)


def _registry():
    registry, tools = ToolRegistry(), {}
    for name in ("file_write", "pytest", "http_request", "playwright"):
        tools[name] = FakeTool([OK])
        registry.register(name, tools[name])
    return registry, tools


@pytest.mark.parametrize(
    "tool, args, message",
    [
        ("file_write", {"path": "generated/test_a.py"}, "missing required parameter 'content'"),
        ("file_write", {"path": 1, "content": "x"}, "'path' must be str"),
        ("pytest", {}, "missing required parameter 'paths'"),
        ("pytest", {"paths": "generated/test_a.py"}, "'paths' must be list"),
        ("pytest", {"paths": ["ok.py", 3]}, "only str items"),
        ("pytest", {"paths": ["a.py"], "shell": "rm -rf /"}, "unknown parameter"),
        ("http_request", {"method": "GET"}, "missing required parameter 'route'"),
        ("http_request", {"method": "GET", "route": "/", "json": "[]"}, "'json' must be dict"),
    ],
)
def test_invalid_arguments_rejected_and_tool_not_run(tool, args, message):
    registry, tools = _registry()

    with pytest.raises(ToolArgumentError, match=message):
        registry.call(tool, **args)

    assert tools[tool].calls == []


def test_optional_parameters_may_be_omitted():
    registry, tools = _registry()

    registry.call("http_request", method="GET", route="/health")

    assert tools["http_request"].calls == [{"method": "GET", "route": "/health"}]


def test_bool_is_not_accepted_as_int():
    with pytest.raises(ToolArgumentError):
        Param(int).check("n", True)


def test_traced_call_records_schema_mismatch_without_running_tool(harness):
    registry, tools = _registry()

    with pytest.raises(ToolArgumentError):
        TracedToolRegistry(registry, harness.inst).call("pytest", paths="not-a-list")

    span = harness.one("tool.pytest")
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["qa.failure.symptom"] == "SCHEMA_MISMATCH"
    assert harness.named("attempt") == []
    assert tools["pytest"].calls == []


def test_custom_schema_overrides_default():
    registry = ToolRegistry()
    tool = FakeTool([OK])
    registry.register("pytest", tool, schema={"only": Param(int)})

    registry.call("pytest", only=1)

    assert tool.calls == [{"only": 1}]
