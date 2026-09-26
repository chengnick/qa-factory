"""Build synthetic traces (span dicts in the trace.json format) for classification tests."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

_ids = itertools.count(1)


class TraceBuilder:
    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self.root = self.span("qa.run", None)

    def span(self, name: str, parent: dict | None, *, error: str | None = None, exc: str | None = None,
             attrs: dict | None = None, events: list | None = None, upstream: str | None = None) -> dict:  # fmt: skip
        events = list(events or [])
        if exc:
            event = {"exception.type": exc, "exception.message": error or exc}
            if upstream:
                event["exception.upstream"] = upstream
            events.append({"name": "exception", "timestamp": None, "attributes": event})
        span = {
            "span_id": f"{next(_ids):016x}",
            "parent_span_id": parent["span_id"] if parent else None,
            "name": name,
            "status": {"code": "ERROR" if (error or exc) else "OK", "message": error or exc},
            "attributes": dict(attrs or {}),
            "events": events,
        }
        self.spans.append(span)
        return span

    def agent(self, name: str, **kw) -> dict:
        return self.span(f"agent.{name}", self.root, attrs={"qa.agent.name": name}, **kw)

    def tool(self, parent: dict, tool: str, **kw) -> dict:
        attrs = {"qa.tool.name": tool, **kw.pop("attrs", {})}
        return self.span(f"tool.{tool}", parent, attrs=attrs, **kw)

    def pytest_run(self, parent: dict, exit_code: int, results: list[tuple[str, str, str]] = (), tool: str = "pytest", **kw) -> dict:
        events = [{"name": "qa.test.result", "timestamp": None,
                   "attributes": {"qa.test.id": n, "qa.test.outcome": o, "qa.test.message": m}} for n, o, m in results]  # fmt: skip
        collection = sum(1 for n, o, _ in results if "::" not in n and o == "ERROR")
        attrs = {"qa.tool.exit_code": exit_code, "qa.test.collection_errors": collection}
        return self.tool(parent, tool, error="failed" if exit_code else None, attrs=attrs, events=events, **kw)

    def health(self, parent: dict, ok: bool = True, exc: str | None = None) -> dict:
        attrs = {"qa.http.route": "/health", "qa.http.method": "GET"}
        if exc is None:
            attrs["qa.http.status_code"] = 200 if ok else 503
        return self.tool(parent, "http_request", attrs=attrs, error=None if ok and exc is None else (exc or "503"), exc=exc)


@pytest.fixture
def trace() -> TraceBuilder:
    return TraceBuilder()
