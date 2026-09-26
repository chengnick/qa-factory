"""Trace JSON documents follow spec v2 §3.4 (carried over by spec v3 §4.4; text in git history, docs/spec-v2.md @ 639bc1c)."""

import json
import re

from agents.contracts import RequirementInput
from observability.instrument import FileContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import create_tracer_provider, get_tracer, new_instrumentation
from pipeline import run_pipeline
from testing import scripts
from testing.fake_clock import FakeClock

ISO_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _run(tmp_dir, scenario="flaky", requirement_id="REQ-005"):
    exporter = JsonFileSpanExporter(tmp_dir)
    clock = FakeClock()
    provider, inst = new_instrumentation(clock, FileContentSink(tmp_dir), exporter)
    result = run_pipeline(
        RequirementInput(requirement_id, "text"),
        llm=scripts.fake_llm(requirement_id, clock),
        tools=scripts.fake_tools(requirement_id, scenario, clock),
        inst=inst,
        sut_bugs=["B02"],
    )
    provider.shutdown()
    return result, exporter


def test_one_file_per_trace_named_by_trace_id(tmp_dir):
    r1, _ = _run(tmp_dir)
    r2, _ = _run(tmp_dir, scenario="pass")

    files = sorted(p.name for p in tmp_dir.glob("*.json"))
    assert files == sorted([f"{r1.trace_id}.json", f"{r2.trace_id}.json"])
    assert r1.trace_id != r2.trace_id


def test_document_schema(tmp_dir):
    result, _ = _run(tmp_dir)
    doc = json.loads((tmp_dir / f"{result.trace_id}.json").read_text(encoding="utf-8"))

    assert set(doc) == {"trace_id", "run", "spans"}
    assert re.fullmatch(r"[0-9a-f]{32}", doc["trace_id"])
    assert doc["run"] == {
        "requirement_id": "REQ-005",
        "sut_bugs": ["B02"],
        "started_at": "2026-09-25T10:00:00.000Z",
        "duration_ms": 15970.0,
        "verdict": "FLAKY",
    }
    for span in doc["spans"]:
        assert set(span) == {"span_id", "parent_span_id", "name", "start_time", "end_time", "duration_ms", "status", "attributes", "events"}
        assert re.fullmatch(r"[0-9a-f]{16}", span["span_id"])
        assert ISO_MS.match(span["start_time"]) and ISO_MS.match(span["end_time"])
        assert span["status"]["code"] in {"OK", "ERROR"}
        for event in span["events"]:
            assert set(event) == {"name", "timestamp", "attributes"}


def test_span_count_and_links(tmp_dir):
    result, _ = _run(tmp_dir)
    doc = json.loads((tmp_dir / f"{result.trace_id}.json").read_text(encoding="utf-8"))
    spans = doc["spans"]

    # qa.run + 5 agents + 3 llm.chat + 2 file_write + pytest(2 attempts) + http + playwright(1 attempt)
    assert len(spans) == 1 + 5 + 3 + 2 + 3 + 1 + 2
    ids = {s["span_id"] for s in spans}
    roots = [s for s in spans if s["parent_span_id"] is None]
    assert [r["name"] for r in roots] == ["qa.run"]
    assert all(s["parent_span_id"] in ids for s in spans if s["parent_span_id"])
    assert spans[0]["name"] == "qa.run"  # pre-order: parents before children
    seen = set()
    for s in spans:
        assert s["parent_span_id"] is None or s["parent_span_id"] in seen
        seen.add(s["span_id"])


def test_attempt_spans_serialized_like_spec_example(tmp_dir):
    result, _ = _run(tmp_dir)
    doc = json.loads((tmp_dir / f"{result.trace_id}.json").read_text(encoding="utf-8"))

    attempts = [s for s in doc["spans"] if s["name"] == "attempt"][:2]
    assert attempts[0]["status"]["code"] == "ERROR"
    assert attempts[0]["attributes"] == {"qa.retry.attempt": 1, "qa.failure.symptom": "TIMEOUT"}
    assert attempts[1]["status"] == {"code": "OK", "message": None}
    assert attempts[0]["duration_ms"] == 3200.0


def test_artifacts_written_under_trace_dir(tmp_dir):
    result, _ = _run(tmp_dir, scenario="defect")
    doc = json.loads((tmp_dir / f"{result.trace_id}.json").read_text(encoding="utf-8"))

    tool = next(s for s in doc["spans"] if s["name"] == "tool.pytest")
    event = next(e for e in tool["events"] if e["name"] == "stdout.tail")
    artifact = tmp_dir / event["attributes"]["artifact"]
    assert artifact.parent == tmp_dir / result.trace_id / "artifacts"
    assert "AssertionError: expected 409, got 200" in artifact.read_text(encoding="utf-8")


def test_shutdown_flushes_trace_whose_root_never_ended(tmp_dir):
    exporter = JsonFileSpanExporter(tmp_dir)
    provider = create_tracer_provider(exporter)
    tracer = get_tracer(provider)
    root = tracer.start_span("qa.run")
    from opentelemetry import trace

    with tracer.start_as_current_span("agent.requirement", context=trace.set_span_in_context(root)):
        pass
    assert exporter.written == []

    provider.shutdown()

    (path,) = exporter.written
    assert [s["name"] for s in json.loads(path.read_text(encoding="utf-8"))["spans"]] == ["agent.requirement"]
