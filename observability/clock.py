"""Injectable clock: spans take their timestamps from here, retries sleep through it."""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now_ns(self) -> int:
        return time.time_ns()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
