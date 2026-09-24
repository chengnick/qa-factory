"""benchmark/bugs.yaml, sut/, requirements and reference tests must agree with each other."""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from sut.bugs import KNOWN_BUGS

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = yaml.safe_load((ROOT / "benchmark" / "bugs.yaml").read_text(encoding="utf-8"))
IDS = [b["id"] for b in MANIFEST]
FLAG_CALL = re.compile(r'is_enabled\("(B\d{2})"\)')
SUT_FLAG_IDS = Counter(m for f in (ROOT / "sut").rglob("*.py") for m in FLAG_CALL.findall(f.read_text(encoding="utf-8")))
REF_TESTS = sorted((ROOT / "benchmark" / "reference_tests").glob("test_b*.py"))


def test_manifest_schema():
    required = {"id", "title", "surface", "category", "requirement_ref"}
    for bug in MANIFEST:
        assert set(bug) == required, bug
        assert re.fullmatch(r"B\d{2}", bug["id"])
        assert bug["surface"] in {"api", "ui"}
    assert len(IDS) == len(set(IDS)), "duplicate bug ids"


def test_manifest_size_and_coverage():
    assert 8 <= len(MANIFEST) <= 12
    assert len({b["category"] for b in MANIFEST}) >= 5


def test_sut_known_bugs_match_manifest():
    assert KNOWN_BUGS == set(IDS)


@pytest.mark.parametrize("bug", MANIFEST, ids=IDS)
def test_requirement_doc_exists(bug):
    assert (ROOT / "benchmark" / "requirements" / f"{bug['requirement_ref']}.md").is_file()


@pytest.mark.parametrize("bug_id", IDS)
def test_every_bug_has_an_injection_point(bug_id):
    assert SUT_FLAG_IDS[bug_id] >= 1, f'no is_enabled("{bug_id}") in sut/'


def test_no_injection_point_outside_manifest():
    assert set(SUT_FLAG_IDS) <= set(IDS)


@pytest.mark.parametrize("bug_id", IDS)
def test_exactly_one_reference_test_per_bug(bug_id):
    matches = [p.name for p in REF_TESTS if p.name.startswith(f"test_{bug_id.lower()}_")]
    assert len(matches) == 1, matches


def test_no_orphan_reference_tests():
    orphans = [p.name for p in REF_TESTS if p.name[5:8].upper() not in IDS]
    assert not orphans
