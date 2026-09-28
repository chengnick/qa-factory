"""Phase 5 runner: the freeze (benchmark/frozen.yaml), the test / phase5 datasets and per-set metrics.

No sealed bug is enabled here: the only test-set combination used is a clean run (REQ-003 without bugs).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evaluation import frozen
from evaluation import run as runner
from evaluation.run import RunnerRefused, check_frozen, combinations, run_dataset
from testing.scripts import dry_run_llm

MODEL = "gemini-3.5-flash-lite"


@pytest.fixture
def frozen_file(tmp_dir: Path, monkeypatch) -> Path:
    path = tmp_dir / "frozen.yaml"
    frozen.write(MODEL, path)
    monkeypatch.setattr(runner, "FROZEN", path)
    return path


def test_freeze_records_every_checked_condition(frozen_file):
    doc = yaml.safe_load(frozen_file.read_text(encoding="utf-8"))
    assert set(frozen.CHECKED) <= set(doc)
    assert doc["prompt_version"] == "v3" and doc["model"] == MODEL and doc["temperature"] == 0.0
    assert doc["isolation"] == "L1" and doc["max_rounds"] == 1 and doc["rounds"] == 5
    assert len(doc["combinations"]["dev"]) == 6 and len(doc["combinations"]["test"]) == 12


def test_freeze_is_written_once(frozen_file):
    with pytest.raises(FileExistsError):
        frozen.write(MODEL, frozen_file)


def test_test_and_phase5_datasets_need_the_freeze(tmp_dir, monkeypatch):
    monkeypatch.setattr(runner, "FROZEN", tmp_dir / "missing.yaml")
    assert len(combinations("dev")) == 6
    for dataset in ("test", "phase5"):
        with pytest.raises(RunnerRefused, match="sealed"):
            combinations(dataset)


def test_phase5_is_18_combinations(frozen_file):
    test = combinations("test")
    assert len(test) == 12 and len(combinations("phase5")) == 18
    assert ("REQ-002", ["B06"]) in test and ("REQ-004", []) in test and ("REQ-002", []) not in test


def test_matching_checkout_passes_the_freeze_check(frozen_file):
    assert check_frozen(MODEL, path=frozen_file) == frozen.file_sha256(frozen_file)


@pytest.mark.parametrize("field, value", [("prompt_sha256", "0" * 64), ("model", "another-model"), ("isolation", "L0+"), ("max_rounds", 3)])
def test_any_changed_condition_is_refused(frozen_file, field, value):
    doc = yaml.safe_load(frozen_file.read_text(encoding="utf-8"))
    doc[field] = value
    frozen_file.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(RunnerRefused, match=f"contaminated.*{field}"):
        check_frozen(MODEL, path=frozen_file)


def test_frozen_check_cli_reports_mismatches(frozen_file, monkeypatch, capsys):
    monkeypatch.setattr(frozen, "FROZEN", frozen_file)
    assert frozen.main(["check", "--model", MODEL]) == 0
    assert frozen.main(["check", "--model", "another-model"]) == 1
    assert "MISMATCH model" in capsys.readouterr().out


def test_metrics_are_reported_per_set(tmp_dir, frozen_file):
    summary = run_dataset(
        dataset="phase5", rounds=1, llm_factory=dry_run_llm, llm_kind="fake", model="fake-model",
        artifacts_dir=tmp_dir / "artifacts", results_dir=tmp_dir / "results",
        only=[("REQ-005", ["B02"]), ("REQ-003", [])], log=lambda _: None, frozen_sha256="abc",
    )  # fmt: skip

    assert [(r["requirement_id"], r["set"]) for r in summary["runs"]] == [("REQ-005", "dev"), ("REQ-003", "test")]
    by_set = summary["metrics_by_set"]
    assert by_set["dev"]["true_detection_rate"]["pooled"] == "0/1"  # the dry-run test does not look for B02
    assert by_set["test"]["false_positive_rate_surface"]["pooled"] == "0/1"
    md = (tmp_dir / "results" / "summary.md").read_text(encoding="utf-8")
    assert "## Dev set" in md and "## Test set (held out" in md and "frozen.yaml` sha256 `abc`" in md
    meta = json.loads((tmp_dir / "results" / summary["runs"][1]["run_id"] / "meta.json").read_text(encoding="utf-8"))
    assert meta["set"] == "test" and meta["frozen_sha256"] == "abc"


def test_single_set_summary_keeps_one_metrics_block(tmp_dir):
    summary = run_dataset(
        dataset="dev", rounds=1, llm_factory=dry_run_llm, llm_kind="fake", model="fake-model",
        artifacts_dir=tmp_dir / "artifacts", results_dir=tmp_dir / "results", only=[("REQ-005", [])], log=lambda _: None,
    )  # fmt: skip
    assert "metrics_by_set" not in summary
    assert "## Metrics (spec v3 §11.2)" in (tmp_dir / "results" / "summary.md").read_text(encoding="utf-8")
