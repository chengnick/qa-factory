"""Dev / test split of the seeded bugs (spec v3 §3.2, §3.3).

The pipeline may run the test set only once Phase 5 has frozen the prompt (benchmark/frozen.yaml).
"""

from __future__ import annotations

from collections.abc import Iterable

DEV_BUGS = frozenset({"B02", "B03", "B04"})
TEST_BUGS = frozenset({"B01", "B05", "B06", "B07", "B08", "B09", "B10"})

# Requirement each bug is exercised through (spec v3 §3.2, §11.1).
DEV_COMBINATIONS = (("REQ-005", "B02"), ("REQ-007", "B03"), ("REQ-002", "B04"))
TEST_COMBINATIONS = (
    ("REQ-003", "B01"),
    ("REQ-004", "B05"),
    ("REQ-002", "B06"),
    ("REQ-008", "B07"),
    ("REQ-006", "B08"),
    ("REQ-009", "B09"),
    ("REQ-004", "B10"),
)
DEV_REQUIREMENTS = tuple(dict.fromkeys(req for req, _ in DEV_COMBINATIONS))
# Clean runs of the test set: its requirements minus those already in the dev set (REQ-002 is shared, spec v3 §3.3).
TEST_CLEAN_REQUIREMENTS = tuple(dict.fromkeys(req for req, _ in TEST_COMBINATIONS if req not in DEV_REQUIREMENTS))


def dataset_of(bugs: Iterable[str]) -> str:
    """"clean" (no bugs), "dev" (dev bugs only) or "test" (any test-set bug)."""
    bugs = set(bugs)
    unknown = bugs - DEV_BUGS - TEST_BUGS
    if unknown:
        raise ValueError(f"unknown bug ids: {sorted(unknown)}")
    if not bugs:
        return "clean"
    return "test" if bugs & TEST_BUGS else "dev"


def set_of(requirement_id: str, bugs: Iterable[str]) -> str:
    """Which evaluation set a combination belongs to: "dev" or "test". A clean run belongs to the set of its
    requirement; REQ-002 is a dev requirement (its clean runs were part of the dev set since Phase 2R)."""
    bugs = set(bugs)
    if bugs:
        return "test" if dataset_of(bugs) == "test" else "dev"
    if requirement_id in DEV_REQUIREMENTS:
        return "dev"
    if requirement_id in TEST_CLEAN_REQUIREMENTS:
        return "test"
    raise ValueError(f"{requirement_id} is in neither the dev nor the test set")
