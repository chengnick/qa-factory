"""Property 5: W01 (test weakened). A test that failed in round 1 and passes in round 2 after losing assertions
(plain assert, pytest.raises or expect) always triggers W01; one that only gained assertions never does."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

import evaluation.workflow as workflow

NODE = "generated/test_req005_api.py::test_rule"
PATH = "generated/test_req005_api.py"
KINDS = ("assert", "raises", "expect")


def _statement(kind: str, i: int) -> str:
    return {
        "assert": f"    assert value == {i}, 'v'\n",
        "raises": f"    with pytest.raises(ValueError):\n        int('x{i}')\n",
        "expect": f"    expect(page.locator('#a{i}')).to_have_count({i})\n",
    }[kind]


def _source(assertions: list[tuple[str, int]]) -> str:
    body = "".join(_statement(k, i) for k, i in assertions)
    return "import pytest\nfrom playwright.sync_api import expect\n\n\ndef test_rule(page):\n    value = 1\n" + body


def _rounds(before: list[tuple[str, int]], after: list[tuple[str, int]]) -> list:
    return [
        workflow.Round(1, {PATH: _source(before)}, [{"node_id": NODE, "outcome": "FAIL", "message": "assert 1 == 0"}]),
        workflow.Round(2, {PATH: _source(after)}, [{"node_id": NODE, "outcome": "PASS", "message": ""}]),
    ]


assertion_lists = st.lists(st.sampled_from(KINDS), min_size=1, max_size=6).map(lambda ks: [(k, i) for i, k in enumerate(ks)])


@given(data=st.data(), before=assertion_lists)
def test_removing_assertions_from_a_failing_test_that_then_passes_triggers_w01(data, before):
    removed = data.draw(st.sets(st.integers(0, len(before) - 1), min_size=1))
    after = [a for i, a in enumerate(before) if i not in removed]
    rules = [v.rule for v in workflow.evaluate_rounds(_rounds(before, after))]
    assert "W01" in rules, f"removed {[before[i][0] for i in sorted(removed)]} of {[k for k, _ in before]}: no W01"


@given(data=st.data(), before=assertion_lists)
def test_adding_assertions_never_triggers_w01(data, before):
    added = data.draw(st.lists(st.sampled_from(KINDS), min_size=1, max_size=3))
    after = before + [(k, 100 + i) for i, k in enumerate(added)]
    assert "W01" not in [v.rule for v in workflow.evaluate_rounds(_rounds(before, after))]
