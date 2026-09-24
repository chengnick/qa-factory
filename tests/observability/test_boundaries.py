"""Architectural rules: agents never touch OTel; a fake run needs no network and no API key."""

import ast
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IN_AGENTS = ("opentelemetry", "observability")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", sorted((ROOT / "agents").glob("*.py")), ids=lambda p: p.name)
def test_agents_do_not_import_otel_or_observability(path):
    bad = {m for m in _imports(path) if m.split(".")[0] in FORBIDDEN_IN_AGENTS}
    assert not bad, f"{path.name} imports {bad}"


def test_agents_do_not_construct_llm_clients():
    for path in (ROOT / "agents").glob("*.py"):
        imported = _imports(path)
        assert not {m for m in imported if m.startswith(("llm.adapters", "anthropic", "openai", "testing"))}, path.name


def test_fake_run_needs_no_network_and_no_api_key(harness, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    result = harness.run()

    assert result.error is None and result.verdict == "FLAKY"


def test_cli_writes_trace_file(tmp_dir, capsys):
    import json

    import app

    code = app.main(["--requirement", "REQ-005", "--llm", "fake", "--sut-bugs", "B02", "--traces-dir", str(tmp_dir)])

    assert code == 0
    (trace_file,) = tmp_dir.glob("*.json")
    doc = json.loads(trace_file.read_text(encoding="utf-8"))
    assert doc["run"]["requirement_id"] == "REQ-005" and doc["run"]["verdict"] == "FLAKY"
    assert "verdict: FLAKY" in capsys.readouterr().out
