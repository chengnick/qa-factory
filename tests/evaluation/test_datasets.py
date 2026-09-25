"""Dev / test split (spec v3 §3.2) agrees with the bug manifest."""

from pathlib import Path

import pytest
import yaml

from benchmark.datasets import DEV_BUGS, DEV_COMBINATIONS, TEST_BUGS, dataset_of

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
