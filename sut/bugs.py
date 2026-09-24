"""Seeded-bug flags.

`SUT_BUGS=B01,B04` turns bugs on. Every injection point in the SUT calls
`is_enabled("Bxx")` with a literal id, so `grep 'is_enabled("B'` finds them all.
"""

from __future__ import annotations

import os

ENV_VAR = "SUT_BUGS"

KNOWN_BUGS: frozenset[str] = frozenset(f"B{n:02d}" for n in range(1, 11))


def parse(raw: str | None) -> frozenset[str]:
    """Parse a SUT_BUGS value. Unknown ids raise, so a typo never silently yields a clean SUT."""
    if not raw:
        return frozenset()
    ids = {part.strip().upper() for part in raw.split(",") if part.strip()}
    unknown = ids - KNOWN_BUGS
    if unknown:
        raise ValueError(f"Unknown bug id(s) in {ENV_VAR}: {sorted(unknown)}")
    return frozenset(ids)


def enabled_bugs() -> frozenset[str]:
    return parse(os.environ.get(ENV_VAR))


def is_enabled(bug_id: str) -> bool:
    """Read the environment on every call: no cached state, trivially monkeypatchable."""
    if bug_id not in KNOWN_BUGS:
        raise KeyError(f"is_enabled() called with unknown bug id {bug_id!r}")
    return bug_id in enabled_bugs()
