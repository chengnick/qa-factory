"""Dev / test split (spec v3 §3.2) agrees with the bug manifest."""

from pathlib import Path

import pytest
import yaml

from benchmark.datasets import DEV_BUGS, DEV_COMBINATIONS, TEST_BUGS, TEST_CLEAN_REQUIREMENTS, TEST_COMBINATIONS, dataset_of, set_of

MANIFEST = yaml.safe_load((Path(__file__).resolve().parents[2] / "benchmark" / "bugs.yaml").read_text(encoding="utf-8"))


def test_split_covers_manifest_exactly_once():
    assert DEV_BUGS | TEST_BUGS == {b["id"] for b in MANIFEST}
    assert not DEV_BUGS & TEST_BUGS


def test_dev_combinations_use_each_bugs_requirement():
    refs = {b["id"]: b["requirement_ref"] for b in MANIFEST}
    assert sorted(bug for _, bug in DEV_COMBINATIONS) == sorted(DEV_BUGS)
    assert all(refs[bug] == req for req, bug in DEV_COMBINATIONS)


@pytest.mark.parametrize(
    "bugs, dataset",
    [([], "clean"), (["B02"], "dev"), (["B02", "B04"], "dev"), (["B01"], "test"), (["B02", "B06"], "test")],
)
def test_dataset_of(bugs, dataset):
    assert dataset_of(bugs) == dataset


def test_unknown_bug_rejected():
    with pytest.raises(ValueError):
        dataset_of(["B99"])


def test_test_combinations_use_each_bugs_requirement():
    refs = {b["id"]: b["requirement_ref"] for b in MANIFEST}
    assert sorted(bug for _, bug in TEST_COMBINATIONS) == sorted(TEST_BUGS)
    assert all(refs[bug] == req for req, bug in TEST_COMBINATIONS)


def test_clean_runs_cover_every_requirement_once():
    """18 Phase 5 combinations: 3 + 7 bugged, 3 + 5 clean; REQ-002's clean run stays in the dev set."""
    assert TEST_CLEAN_REQUIREMENTS == ("REQ-003", "REQ-004", "REQ-008", "REQ-006", "REQ-009")
    assert set_of("REQ-002", []) == "dev" and set_of("REQ-004", []) == "test"
    assert set_of("REQ-002", ["B06"]) == "test" and set_of("REQ-002", ["B04"]) == "dev"
    with pytest.raises(ValueError):
        set_of("REQ-001", [])
