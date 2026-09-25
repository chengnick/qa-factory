"""Secrets never survive into span attributes, events, artifacts or trace files."""

import json

import pytest

from observability.instrument import FileContentSink, Instrumentation, TracedToolRegistry
from observability.json_exporter import JsonFileSpanExporter
from observability.redact import MASK, redact, redact_value
from observability.setup import create_tracer_provider, get_tracer
from testing.fake_clock import FakeClock
from testing.fake_tool import FakeTool
from tools.registry import ToolRegistry, ToolResult

ANTHROPIC_KEY = "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
OPENAI_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrSt1234"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
GH_TOKEN = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz012345"
SECRETS = [ANTHROPIC_KEY, OPENAI_KEY, AWS_KEY, GH_TOKEN, "hunter2", "s3cr3t-value", "eyJhbGciOiJIUzI1NiJ9.payload.sig"]


@pytest.mark.parametrize(
    "text, secret",
    [
        (f"using key {ANTHROPIC_KEY} now", ANTHROPIC_KEY),
        (f"OPENAI={OPENAI_KEY}", OPENAI_KEY),
        (f"aws {AWS_KEY}", AWS_KEY),
        (f"token {GH_TOKEN}", GH_TOKEN),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "eyJhbGciOiJIUzI1NiJ9.payload.sig"),
        ("password=hunter2", "hunter2"),
        ('{"api_key": "s3cr3t-value"}', "s3cr3t-value"),
        ("export ANTHROPIC_API_KEY=abc123def", "abc123def"),
        ("db_password: hunter2", "hunter2"),
    ],
)
def test_redact_masks_secret_shapes(text, secret):
    out = redact(text)
    assert secret not in out
    assert MASK in out


@pytest.mark.parametrize("text", ["1 passed in 0.41s", "GET /api/tasks/5 -> 200", "tokens used: 120", "task-secretary-notes"])
def test_redact_leaves_ordinary_text_alone(text):
    assert redact(text) == text


def test_redact_value_recurses():
    value = {"a": [f"k={ANTHROPIC_KEY}", ("password=hunter2",)], "n": 3}
    out = redact_value(value)
    assert ANTHROPIC_KEY not in json.dumps(out) and "hunter2" not in json.dumps(out)
    assert out["n"] == 3 and isinstance(out["a"][1], tuple)


def test_secrets_absent_from_spans_artifacts_and_trace_file(tmp_dir):
    exporter = JsonFileSpanExporter(tmp_dir)
    provider = create_tracer_provider(exporter)
    inst = Instrumentation(get_tracer(provider), FakeClock(), FileContentSink(tmp_dir))
    leaky = ToolResult(
        ok=False,
        exit_code=1,
        command=f"pytest --api-key={ANTHROPIC_KEY} -k smoke",
        stdout=f"env ANTHROPIC_API_KEY={ANTHROPIC_KEY}\nAuthorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig\n"
        f"password=hunter2 aws={AWS_KEY} {OPENAI_KEY} {GH_TOKEN}\n{{\"api_key\": \"s3cr3t-value\"}}\n1 failed",
    )
    registry = ToolRegistry()
    registry.register("pytest", FakeTool([leaky]))

    from observability.instrument import traced_run

    with traced_run(inst, "REQ-001") as run:
        TracedToolRegistry(registry, inst).call("pytest", paths=["generated/test_x.py"])
    provider.shutdown()

    written = [p for p in tmp_dir.rglob("*") if p.is_file()]
    assert (tmp_dir / f"{run.trace_id}.json") in written
    assert any("artifacts" in p.parts for p in written)
    for path in written:
        content = path.read_text(encoding="utf-8")
        for secret in SECRETS:
            assert secret not in content, f"{secret!r} leaked into {path.name}"
    doc = json.loads((tmp_dir / f"{run.trace_id}.json").read_text(encoding="utf-8"))
    tool = next(s for s in doc["spans"] if s["name"] == "tool.pytest")
    assert tool["attributes"]["qa.tool.command"] == f"pytest --api-key={MASK} -k smoke"


def test_exporter_redacts_even_unredacted_attributes(tmp_dir):
    """Second line of defence: attributes set without going through instrument helpers."""
    exporter = JsonFileSpanExporter(tmp_dir)
    provider = create_tracer_provider(exporter)
    with get_tracer(provider).start_as_current_span("qa.run") as span:
        span.set_attribute("qa.tool.command", f"curl -H 'x-api-key: {ANTHROPIC_KEY}'")
    provider.shutdown()

    (path,) = exporter.written
    assert ANTHROPIC_KEY not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("text", [f"key {ANTHROPIC_KEY}", f"aws {AWS_KEY}", f"g {GH_TOKEN}", "GEMINI_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrstuv",
                                  "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", 'password="hunter2hunter2"'])  # fmt: skip
def test_find_secret_detects_credential_shapes(text):
    from observability.redact import find_secret

    assert find_secret(text)


@pytest.mark.parametrize("text", ['"tokens": {"input": 2140}', '"gen_ai.usage.input_tokens": 111', "Bearer [REDACTED]",
                                  "api_key=[REDACTED]", "tokens used: 120"])  # fmt: skip
def test_find_secret_ignores_metrics_and_already_masked_values(text):
    from observability.redact import find_secret

    assert find_secret(text) is None
