"""Blind labelling sheet and attribution-accuracy score (spec v3 §11.2)."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

from evaluation.labels import SHEET_FIELDS, blind, collect, main, raw_message, sample, score, stratified

NODE = "generated/test_req005_api.py::test_a"


def _run(root: Path, run_id: str, classifications: list[dict], decisions: list[dict] | None = None, bugs=("B02",)) -> None:
    run = root / run_id
    (run / "generated").mkdir(parents=True)
    (run / "generated" / "test_req005_api.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (run / "meta.json").write_text(json.dumps({"set": "test", "requirement_id": "REQ-005", "sut_bugs": list(bugs)}), encoding="utf-8")
    (run / "classification.json").write_text(json.dumps({"surface": {}, "final": {"classifications": classifications}}), encoding="utf-8")
    if decisions is not None:
        (run / "differential.json").write_text(json.dumps({"decisions": decisions}), encoding="utf-8")


def _c(layer: str, rule: str, evidence: str = "e", test_id: str | None = None, unit: str = "diff") -> dict:
    return {"unit": unit, "layer": layer, "symptom": "ASSERTION", "matched_rule": rule, "evidence": evidence, "test_id": test_id}


@pytest.fixture
def results(tmp_dir: Path) -> Path:
    root = tmp_dir / "results"
    for i in range(12):
        _run(root, f"RUN-20260928-0000{i:02d}-AAAA", [_c("SUT", "R11", "bug build: assert 200 == 409 | cross-validation R11", NODE)],
             [{"node_id": NODE, "bug_outcome": "FAIL", "clean_outcome": "PASS", "decision": "DETECTED", "rule": "R11",
               "evidence": "bug build: assert 200 == 409"}])  # fmt: skip
    for i in range(4):
        _run(root, f"RUN-20260928-0001{i:02d}-BBBB", [_c("TEST", "R12", "x", NODE)],
             [{"node_id": NODE, "bug_outcome": "FAIL", "clean_outcome": "FAIL", "decision": "BROKEN", "rule": "R12",
               "evidence": "fails on a clean SUT: assert 404 == 422"}], bugs=())  # fmt: skip
    for i in range(3):
        _run(root, f"RUN-20260928-0002{i:02d}-CCCC", [_c("PROVIDER", "R3", "LLMUnavailableError: 503", unit="llm")])
    return root


def test_prefixes_and_rule_ids_are_removed():
    assert raw_message("bug build: assert 200 == 409") == "assert 200 == 409"
    assert raw_message("bug build: boom | clean build: bang") == "boom"
    assert raw_message("fails on a clean SUT: assert 404 == 422") == "assert 404 == 422"
    assert raw_message("nondeterministic on identical clean SUTs: bug=FAIL (flip) clean=PASS ()") == "flip"
    assert blind("matched R11U: something | cross-validation R11") == "matched: something"


def test_sheet_rows_hold_the_raw_message_only(results):
    rows = [row for row, _, _ in collect(results)]
    assert tuple(rows[0]) == SHEET_FIELDS and "bug_build" not in rows[0] and "clean_build" not in rows[0]
    obs = {r["observation"] for r in rows}
    assert obs == {"assert 200 == 409", "assert 404 == 422", "LLMUnavailableError: 503"}
    assert all(r["human_layer"] == r["targets_injected_bug"] == r["notes"] == "" for r in rows)


def test_withheld_fields_go_to_the_key_file(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=8)
    with (out / "sheet_key.csv").open(encoding="utf-8-sig", newline="") as f:
        withheld = list(csv.DictReader(f))
    assert {w["observation_original"] for w in withheld if w["bug_build"]} <= {"bug build: assert 200 == 409", "fails on a clean SUT: assert 404 == 422"}
    sheet = (out / "sheet.csv").read_text(encoding="utf-8-sig")
    assert "bug build" not in sheet and "clean SUT" not in sheet and "R11" not in sheet and "PASS" not in sheet
    assert (out / "INSTRUCTIONS.md").is_file() and not (out / "README.md").exists()


def test_rows_are_shuffled_with_a_recorded_seed(results, tmp_dir):
    a, b = tmp_dir / "a", tmp_dir / "b"
    sample(results, a, n=8)
    sample(results, b, n=8, order_seed=1)
    ids = lambda d: [r["id"] for r in csv.DictReader((d / "sheet.csv").open(encoding="utf-8-sig", newline=""))]  # noqa: E731
    assert sorted(ids(a)) == sorted(ids(b)) and ids(a) != ids(b)  # same sample, different order
    info = json.loads((a / "key.json").read_text(encoding="utf-8"))["info"]
    assert info["seed"] == 20260928 and info["order_seed"] == 20260929
    assert "20260929" in (a / "INSTRUCTIONS.md").read_text(encoding="utf-8")


def test_stratified_sample_covers_every_layer_and_is_deterministic():
    items = [("SUT", i) for i in range(30)] + [("TEST", i) for i in range(8)] + [("ENV", 0)]
    picked = stratified(items, lambda it: it[0], 12)
    assert Counter(l for l, _ in picked) == Counter({"SUT": 8, "TEST": 3, "ENV": 1})
    assert picked == stratified(items, lambda it: it[0], 12)


def _fill(out: Path, fill) -> None:
    with (out / "sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        fill(r)
    with (out / "sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def test_score_reports_diff_rows_as_the_main_figure(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=8)
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]
    first_diff = {"done": False}

    def fill(r):
        r["human_layer"] = key[r["id"]]["layer"]
        applicable = r["kind"] == "diff" and r["sut_bugs"] != "(clean)"
        r["targets_injected_bug"] = "yes" if applicable else "n.a."
        if r["kind"] == "diff" and not first_diff["done"]:
            r["human_layer"], r["notes"], first_diff["done"] = "UNKNOWN", "spec unclear", True

    _fill(out, fill)
    result = score(out)
    diff, other = result["main_diff"], result["llm_agent"]
    assert (diff["agree"], diff["n"], diff["unknown_labels"]) == (diff["n"] - 1, diff["n"], 1)
    assert (other["agree"], other["n"]) == (3, 3)
    assert result["disagreements"][0]["notes"] == "spec unclear"
    assert "Main figure, diff rows" in (out / "score.md").read_text(encoding="utf-8")


def test_score_refuses_missing_or_inconsistent_labels(results, tmp_dir, capsys):
    out = tmp_dir / "labels"
    sample(results, out, n=8)
    assert main(["score", "--out", str(out)]) == 2
    assert "fix these rows first" in capsys.readouterr().err

    def fill(r):  # every layer filled, but a clean / llm row claims the bug was targeted
        r["human_layer"] = "SUT"
        r["targets_injected_bug"] = "yes"

    _fill(out, fill)
    with pytest.raises(ValueError, match="must be n.a."):
        score(out)


def test_open_target_is_accepted_only_with_a_reason(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=8)

    def fill(r):
        r["human_layer"] = "SUT"
        applicable = r["kind"] == "diff" and r["sut_bugs"] != "(clean)"
        r["targets_injected_bug"] = "" if applicable else "n.a."
        r["notes"] = "cannot tell from the message" if applicable else ""

    _fill(out, fill)
    assert score(out)["targets_injected_bug_bugged_diff"].get("unclear", 0) >= 1


def test_tests_are_copied_and_the_sheet_points_at_the_copies(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=8)
    rows = list(csv.DictReader((out / "sheet.csv").open(encoding="utf-8-sig", newline="")))
    diff_rows = [r for r in rows if r["kind"] == "diff"]
    assert diff_rows and all(r["generated_tests"].startswith("tests/RUN-") for r in diff_rows)
    for r in diff_rows:
        copy = out / r["generated_tests"]
        assert copy.is_file() and copy.parent.name == r["run_id"]
    assert "results" not in (out / "sheet.csv").read_text(encoding="utf-8-sig")
    text = (out / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "benchmark/results/phase5/" in text and "不要打開" in text and "SUT` | `no`" in text and "精確度" in text


def test_score_warns_about_edited_fields_and_missing_ids_but_still_scores(results, tmp_dir):
    out = tmp_dir / "labels"
    sample(results, out, n=8)
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))["key"]
    with (out / "sheet.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["human_layer"] = key[r["id"]]["layer"]
        r["targets_injected_bug"] = "yes" if r["kind"] == "diff" and r["sut_bugs"] != "(clean)" else "n.a."
    rows[0]["observation"] = "edited by hand"
    dropped = rows.pop()["id"]
    rows = list(reversed(rows))  # order does not matter: rows are matched by id
    with (out / "sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    result = score(out)
    assert any("observation" in w for w in result["warnings"]) and any(dropped in w and "missing" in w for w in result["warnings"])
    assert result["all_rows"]["n"] == 7 and result["all_rows"]["agree"] == 7
    assert set(result["by_classifier_layer_all"]) <= {"SUT", "TEST", "PROVIDER"}
    assert all(v["ci95"] for v in result["by_classifier_layer_all"].values())
    md = (out / "score.md").read_text(encoding="utf-8")
    assert "Agreement by the classifier's layer" in md and "precision" in md and "## Warnings" in md
