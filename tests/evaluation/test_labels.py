"""Blind labelling sheet and attribution-accuracy score (spec v3 §11.2)."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from evaluation.labels import blind, collect, main, sample, score, stratified


def _run(root: Path, run_id: str, classifications: list[dict], decisions: list[dict] | None = None) -> None:
    run = root / run_id
    (run / "generated").mkdir(parents=True)
    (run / "generated" / "test_req005_api.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (run / "meta.json").write_text(json.dumps({"set": "test", "requirement_id": "REQ-005", "sut_bugs": ["B02"]}), encoding="utf-8")
    (run / "classification.json").write_text(json.dumps({"surface": {}, "final": {"classifications": classifications}}), encoding="utf-8")
    if decisions is not None:
        (run / "differential.json").write_text(json.dumps({"decisions": decisions}), encoding="utf-8")


def _c(layer: str, rule: str, evidence: str = "e", test_id: str | None = None) -> dict:
    return {"unit": "diff", "layer": layer, "symptom": "ASSERTION", "matched_rule": rule, "evidence": evidence, "test_id": test_id}


@pytest.fixture
def results(tmp_dir: Path) -> Path:
    root = tmp_dir / "results"
    node = "generated/test_req005_api.py::test_a"
    for i in range(12):
        _run(root, f"RUN-20260928-0000{i:02d}-AAAA", [_c("SUT", "R11", "bug build: assert 200 == 409 | cross-validation R11", node)],
             [{"node_id": node, "bug_outcome": "FAIL", "clean_outcome": "PASS", "decision": "DETECTED", "rule": "R11"}])  # fmt: skip
    for i in range(4):
        _run(root, f"RUN-20260928-0001{i:02d}-BBBB", [_c("TEST", "R12"), _c("AGENT", "R18")])
    _run(root, "RUN-20260928-000200-CCCC", [_c("PROVIDER", "R3")])
    return root


def test_rule_ids_are_removed_from_observations():
    assert blind("bug build: assert 200 == 409 | cross-validation R11") == "bug build: assert 200 == 409"
    assert blind("matched R11U: something") == "matched: something"
    assert blind("HTTP 500 from /api/tasks") == "HTTP 500 from /api/tasks"


def test_collect_gives_raw_build_outcomes_but_not_the_decision(results):
    rows = [row for row, _ in collect(results)]
    assert len(rows) == 12 + 8 + 1
    sut = next(r for r in rows if r["test_id"])
    assert (sut["bug_build"], sut["clean_build"], sut["observation"]) == ("FAIL", "PASS", "bug build: assert 200 == 409")
    assert not any("R11" in json.dumps(r) or "DETECTED" in json.dumps(r) for r in rows)
    assert sut["generated_tests"].endswith("generated/test_req005_api.py") and sut["human_layer"] == ""


def test_stratified_sample_covers_every_layer_and_is_deterministic():
    items = [("SUT", i) for i in range(30)] + [("TEST", i) for i in range(8)] + [("ENV", 0)]
    picked = stratified(items, lambda it: it[0], 12)
    assert Counter(l for l, _ in picked) == Counter({"SUT": 8, "TEST": 3, "ENV": 1})
    assert picked == stratified(items, lambda it: it[0], 12)


def test_sample_writes_a_blind_sheet_and_a_separate_key(results, tmp_dir):
    out = tmp_dir / "labels"
    info = sample(results, out, n=10)
    assert info["sampled"] == 10 and set(info["sample_by_layer"]) == {"SUT", "TEST", "AGENT", "PROVIDER"}
    sheet = (out / "sheet.csv").read_text(encoding="utf-8-sig")
    assert "R11" not in sheet and "R12" not in sheet and "matched_rule" not in sheet
    assert len(json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]) == 10
    with pytest.raises(FileExistsError):
        sample(results, out, n=10)


def test_score_compares_layers(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=6)
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]
    with (out / "sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):  # agree on all but the first row
        r["human_layer"] = "UNKNOWN" if i == 0 else key[r["id"]]["layer"].lower()
    with (out / "sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    result = score(out)
    assert (result["agree"], result["n"]) == (5, 6)
    assert result["disagreements"][0]["human"] == "UNKNOWN"
    assert "5/6" in (out / "score.md").read_text(encoding="utf-8")


def test_score_refuses_unlabelled_or_invalid_rows(results, tmp_dir, capsys):
    out = tmp_dir / "labels"
    sample(results, out, n=4)
    assert main(["score", "--out", str(out)]) == 2
    assert "unlabelled rows" in capsys.readouterr().err
