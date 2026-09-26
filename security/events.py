"""Security events (spec v3 §7), kept separate from failure classification.

Each event is recorded on the current span (event `security.<TYPE>`) and collected per run into
security_events.json. `executed` says whether the action actually happened: a refused action is
always `executed: false`; any `executed: true` event means a safeguard failed (`breach`).
Evidence is redacted before it is stored anywhere.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from opentelemetry import trace

from observability.redact import redact

EVENT_TYPES = (
    "PERMISSION_DENIED",
    "INVALID_TOOL_CALL",
    "EVIDENCE_TAMPER_ATTEMPT",
    "PROTECTED_PATH_WRITE",
    "SECRET_ACCESS",
    "WORKFLOW_VIOLATION",
    "GOAL_DRIFT",
)
EVIDENCE_LIMIT = 300


@dataclass(frozen=True)
class SecurityEvent:
    type: str
    run_id: str | None
    span_id: str | None
    agent: str | None
    action: str
    target: str
    executed: bool
    evidence: str


class SecurityRecorder:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id
        self._events: list[SecurityEvent] = []
        self._lock = threading.Lock()

    def record(self, type: str, *, agent: str | None, action: str, target: str, executed: bool, evidence: str) -> SecurityEvent:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown security event type {type!r}")
        span = trace.get_current_span()
        ctx = span.get_span_context()
        span_id = format(ctx.span_id, "016x") if ctx.is_valid else None
        event = SecurityEvent(type, self.run_id, span_id, agent, action, redact(target), executed, redact(evidence)[:EVIDENCE_LIMIT])
        if ctx.is_valid:
            span.add_event(
                f"security.{type}",
                {"security.agent": agent or "", "security.action": action, "security.target": event.target,
                 "security.executed": executed, "security.evidence": event.evidence},  # fmt: skip
            )
        with self._lock:
            self._events.append(event)
        return event

    @property
    def events(self) -> list[SecurityEvent]:
        with self._lock:
            return list(self._events)

    @property
    def breach(self) -> bool:
        return any(e.executed for e in self.events)

    def to_json(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "breach": self.breach, "events": [asdict(e) for e in self.events]}

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
