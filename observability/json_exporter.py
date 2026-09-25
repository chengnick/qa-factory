"""JsonFileSpanExporter: one JSON document per trace, format per spec v2 §3.4 (carried over by spec v3 §4.4; text in git history, docs/spec-v2.md @ 639bc1c).

Spans are buffered per trace and the file is written when the root span ends.
Everything is passed through redact() on the way out.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from observability.redact import redact_value


def _iso(ns: int | None) -> str | None:
    if ns is None:
        return None
    dt = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{(ns // 1_000_000) % 1000:03d}Z"


def _duration_ms(span: ReadableSpan) -> float | None:
    if span.start_time is None or span.end_time is None:
        return None
    return round((span.end_time - span.start_time) / 1e6, 3)


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    return {
        "span_id": format(span.context.span_id, "016x"),
        "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
        "name": span.name,
        "start_time": _iso(span.start_time),
        "end_time": _iso(span.end_time),
        "duration_ms": _duration_ms(span),
        "status": {"code": span.status.status_code.name, "message": span.status.description},
        "attributes": {k: _plain(v) for k, v in (span.attributes or {}).items()},
        "events": [
            {"name": e.name, "timestamp": _iso(e.timestamp), "attributes": {k: _plain(v) for k, v in (e.attributes or {}).items()}}
            for e in span.events
        ],
    }


def _tree_order(spans: list[ReadableSpan]) -> list[ReadableSpan]:
    """Pre-order: parent before children, siblings by start time."""
    children: dict[int | None, list[ReadableSpan]] = defaultdict(list)
    ids = {s.context.span_id for s in spans}
    for s in spans:
        parent = s.parent.span_id if s.parent and s.parent.span_id in ids else None
        children[parent].append(s)
    ordered: list[ReadableSpan] = []

    def walk(parent: int | None) -> None:
        for s in sorted(children[parent], key=lambda x: (x.start_time or 0)):
            ordered.append(s)
            walk(s.context.span_id)

    walk(None)
    return ordered


def trace_document(trace_id: int, spans: list[ReadableSpan]) -> dict[str, Any]:
    root = next((s for s in spans if s.parent is None), None)
    attrs = dict(root.attributes or {}) if root else {}
    doc = {
        "trace_id": format(trace_id, "032x"),
        "run": {
            "requirement_id": attrs.get("qa.run.requirement_id"),
            "sut_bugs": _plain(attrs.get("qa.run.sut_bugs", ())),
            "started_at": _iso(root.start_time) if root else None,
            "duration_ms": _duration_ms(root) if root else None,
            "verdict": attrs.get("qa.verdict"),
        },
        "spans": [span_to_dict(s) for s in _tree_order(spans)],
    }
    return redact_value(doc)


class JsonFileSpanExporter(SpanExporter):
    """Writes {directory}/{trace_id}.json, or {directory}/{filename} when a fixed name is given
    (a per-run directory holds exactly one trace: artifacts/{run_id}/trace.json)."""

    def __init__(self, directory: str | Path, filename: str | None = None) -> None:
        self.directory = Path(directory)
        self.filename = filename
        self._pending: dict[int, list[ReadableSpan]] = defaultdict(list)
        self._lock = threading.Lock()
        self.written: list[Path] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            for span in spans:
                trace_id = span.context.trace_id
                with self._lock:
                    self._pending[trace_id].append(span)
                    if span.parent is not None:
                        continue
                    batch = self._pending.pop(trace_id)
                self._write(trace_id, batch)
        except OSError:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def _write(self, trace_id: int, spans: list[ReadableSpan]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (self.filename or f"{trace_id:032x}.json")
        path.write_text(json.dumps(trace_document(trace_id, spans), ensure_ascii=False, indent=2), encoding="utf-8")
        self.written.append(path)

    def shutdown(self) -> None:
        # Flush traces whose root never ended (crash mid-run) so nothing is silently lost.
        with self._lock:
            pending, self._pending = self._pending, defaultdict(list)
        for trace_id, spans in pending.items():
            self._write(trace_id, spans)
