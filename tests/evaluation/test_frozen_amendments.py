"""Post-evaluation amendments (benchmark/frozen_amendments.yaml): recorded, validated, reported by `frozen check`,
and never a way around the runner's freeze check."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from evaluation import frozen
from evaluation import run as runner
from evaluation.run import RunnerRefused, check_frozen

MODEL = "gemini-3.5-flash-lite"
ENTRY = {"id": "X1", "date": "2026-10-01", "commits": [], "files": ["x.py"], "change": "c", "reason": "r",
         "affects_frozen_fields": [], "changes": {}, "evaluation_impact": "none"}  # fmt: skip


def _write(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"schema": 1, "amendments": entries}, allow_unicode=True), encoding="utf-8")
    return path


def test_the_repository_amendments_are_valid_and_change_no_frozen_field():
    amendments = frozen.load_amendments()
    assert [a["id"] for a in amendments][:4] == ["A1", "A2", "A3", "A4"]
    assert all(not a["affects_frozen_fields"] for a in amendments)


def test_check_on_the_repository_matches_and_lists_the_amendments(capsys, monkeypatch):
    monkeypatch.setattr(frozen, "FROZEN", frozen.REPO_ROOT / "benchmark" / "frozen.yaml")
    assert frozen.main(["check", "--model", MODEL]) == frozen.EXIT_MATCH
    out = capsys.readouterr().out
    assert "matches the freeze;" in out and "recorded amendment(s) after the freeze (none changes a frozen field)" in out
    assert "AMENDMENT A1 " in out and "MISMATCH" not in out


@pytest.mark.parametrize(
    "broken, message",
    [
        ({"reason": None}, "reason must not be empty"),
        ({"extra": 1}, "keys must be exactly"),
        ({"affects_frozen_fields": ["not_a_field"], "changes": {"not_a_field": {"from": 1, "to": 2}}}, "affects_frozen_fields"),
        ({"affects_frozen_fields": ["model"], "changes": {}}, "changes must give"),
        ({"commits": ["0000000"]}, "not in the git history"),
    ],
)
def test_malformed_amendments_are_rejected(tmp_dir, broken, message):
    entry = {**ENTRY, **broken}
    with pytest.raises(frozen.AmendmentError, match=message):
        frozen.load_amendments(_write(tmp_dir / "a.yaml", [entry]))


def test_duplicate_ids_are_rejected(tmp_dir):
    with pytest.raises(frozen.AmendmentError, match="duplicate id"):
        frozen.load_amendments(_write(tmp_dir / "a.yaml", [ENTRY, ENTRY]))


@pytest.fixture
def frozen_file(tmp_dir: Path, monkeypatch) -> Path:
    path = tmp_dir / "frozen.yaml"
    frozen.write(MODEL, path)
    monkeypatch.setattr(frozen, "FROZEN", path)
    monkeypatch.setattr(runner, "FROZEN", path)
    return path


def _change_frozen_value(path: Path, field: str, value) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    old = copy.deepcopy(doc)
    doc[field] = value
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return old


def test_a_recorded_change_is_reported_as_amended_but_the_runner_still_refuses(frozen_file, tmp_dir, monkeypatch, capsys):
    current = frozen.current_conditions(MODEL)["lockfile_sha256"]
    _change_frozen_value(frozen_file, "lockfile_sha256", "f" * 64)  # pretend the lockfile changed after the freeze
    entry = {**ENTRY, "affects_frozen_fields": ["lockfile_sha256"], "changes": {"lockfile_sha256": {"from": "f" * 64, "to": current}}}
    monkeypatch.setattr(frozen, "AMENDMENTS", _write(tmp_dir / "a.yaml", [entry]))

    assert frozen.main(["check", "--model", MODEL]) == frozen.EXIT_AMENDED
    out = capsys.readouterr().out
    assert "AMENDED lockfile_sha256" in out and "test-set runs stay refused" in out and "MISMATCH" not in out
    with pytest.raises(RunnerRefused, match="lockfile_sha256"):
        check_frozen(MODEL, path=frozen_file)


def test_an_amendment_with_other_values_does_not_explain_a_difference(frozen_file, tmp_dir, monkeypatch, capsys):
    _change_frozen_value(frozen_file, "model", "another-model")
    entry = {**ENTRY, "affects_frozen_fields": ["model"], "changes": {"model": {"from": "another-model", "to": "a-third-model"}}}
    monkeypatch.setattr(frozen, "AMENDMENTS", _write(tmp_dir / "a.yaml", [entry]))
    assert frozen.main(["check", "--model", MODEL]) == frozen.EXIT_MISMATCH
    assert "MISMATCH model" in capsys.readouterr().out


def test_invalid_amendments_stop_the_check(frozen_file, tmp_dir, monkeypatch):
    monkeypatch.setattr(frozen, "AMENDMENTS", _write(tmp_dir / "a.yaml", [{**ENTRY, "reason": ""}]))
    assert frozen.main(["check", "--model", MODEL]) == frozen.EXIT_INVALID
