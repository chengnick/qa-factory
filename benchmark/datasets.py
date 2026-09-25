"""Dev / test split of the seeded bugs (spec v3 §3.2, §3.3).

The pipeline may run the test set only once Phase 5 has frozen the prompt (benchmark/frozen.yaml).
"""

from __future__ import annotations

from collections.abc import Iterable

DEV_BUGS = frozenset({"B02", "B03", "B04"})
TEST_BUGS = frozenset({"B01", "B05", "B06", "B07", "B08", "B09", "B10"})

# Requirement each dev bug is exercised through (spec v3 §11.1).
DEV_COMBINATIONS = (("REQ-005", "B02"), ("REQ-007", "B03"), ("REQ-002", "B04"))


def dataset_of(bugs: Iterable[str]) -> str:
    """"clean" (no bugs), "dev" (dev bugs only) or "test" (any test-set bug)."""
    bugs = set(bugs)
    unknown = bugs - DEV_BUGS - TEST_BUGS
    if unknown:
        raise ValueError(f"unknown bug ids: {sorted(unknown)}")
    if not bugs:
        return "clean"
    return "test" if bugs & TEST_BUGS else "dev"
