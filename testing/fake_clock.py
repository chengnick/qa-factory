"""Deterministic clock: time only moves when a test (or a fake) says so."""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_START_NS = int(datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc).timestamp()) * 1_000_000_000


class FakeClock:
    def __init__(self, start_ns: int = DEFAULT_START_NS) -> None:
        self._now_ns = start_ns
        self.sleeps: list[float] = []

    def now_ns(self) -> int:
        return self._now_ns

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time cannot go backwards")
        self._now_ns += round(seconds * 1_000_000_000)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)
