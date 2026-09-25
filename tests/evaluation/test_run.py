"""Multi-round runner: copies, summary, guards (offline, scripted LLM, real SUTs)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation import run as runner
from evaluation.run import RunnerRefused, combinations, contains_secret, copy_run, run_dataset
from testing.scripts import dry_run_llm


def test_dev_dataset_is_three_bugs_plus_their_clean_runs():
    assert combinations("dev") == [
        ("REQ-005", ["B02"]), ("REQ-007", ["B03"]), ("REQ-002", ["B04"]),
        ("REQ-005", []), ("REQ-007", []), ("REQ-002", []),
    ]  # fmt: skip


def test_test_dataset_refused_while_frozen_yaml_is_missing(monkeypatch, tmp_dir):
    monkeypatch.setattr(runner, "FROZEN", tmp_dir / "frozen.yaml")
    with pytest.raises(RunnerRefused, match="frozen.yaml does not exist"):
        combinations("test")


def test_cli_refuses_test_dataset_before_starting_anything(monkeypatch, tmp_dir):
    monkeypatch.setattr(runner, "FROZEN", tmp_dir / "frozen.yaml")
    code = runner.main(["--dataset", "test", "--llm", "fake", "--results-dir", str(tmp_dir / "results"), "--artifacts-dir", str(tmp_dir / "a")])
    assert code == 2
    assert not (tmp_dir / "a").exists() and not (tmp_dir / "results").exists()


def test_cli_refuses_live_run_on_dirty_worktree(monkeypatch, tmp_dir):
    monkeypatch.setattr(runner, "git_commit", lambda: {"sha": "abc", "dirty": True})
    code = runner.main(["--dataset", "dev", "--llm", "gemini", "--model", "m", "--results-dir", str(tmp_dir / "r"), "--artifacts-dir", str(tmp_dir / "a")])
    assert code == 2
    assert not (tmp_dir / "a").exists()


def test_run_dataset_copies_every_run_and_writes_summary(tmp_dir):
    results = tmp_dir / "results"
    summary = run_dataset(
        dataset="dev", rounds=2, llm_factory=dry_run_llm, llm_kind="fake", model="fake-model",
        artifacts_dir=tmp_dir / "artifacts", results_dir=results, only=[("REQ-005", ["B02"]), ("REQ-005", [])],
        log=lambda _: None,
    )  # fmt: skip

    runs = summary["runs"]
    assert [(r["round"], r["sut_bugs"]) for r in runs] == [(1, ["B02"]), (1, []), (2, ["B02"]), (2, [])]  # interleaved
    for r in runs:  # spec v3 §4.3: every listed run_id has its directory under results/
        copied = results / r["run_id"]
        assert (copied / "meta.json").is_file() and (copied / "trace.json").is_file() and (copied / "differential.json").is_file()
        assert (tmp_dir / "artifacts" / r["run_id"]).is_dir()  # original kept, not moved
    # The dry-run test passes on both builds: bugged runs are MISSED, clean runs PASS.
    assert [r["verdict"] for r in runs] == ["MISSED", "PASS", "MISSED", "PASS"]
    m = summary["metrics"]
    assert m["per_bug_detection"]["B02"]["verified"] == "0/2"
    assert m["env_blocked_rate"]["pooled"] == "0/4"
    md = (results / "summary.md").read_text(encoding="utf-8")
    assert all(r["run_id"] in md for r in runs)
    assert json.loads((results / "summary.json").read_text(encoding="utf-8"))["conditions"]["prompt_version"] == "v3"

    with pytest.raises(RunnerRefused, match="never overwritten"):
        run_dataset(dataset="dev", rounds=1, llm_factory=dry_run_llm, llm_kind="fake", model="fake-model",
                    artifacts_dir=tmp_dir / "artifacts", results_dir=results, only=[], log=lambda _: None)  # fmt: skip


def test_copy_skips_runs_containing_secrets_and_never_overwrites(tmp_dir):
    clean_run = tmp_dir / "artifacts" / "RUN-20260101-000000-AAAA"
    leaky_run = tmp_dir / "artifacts" / "RUN-20260101-000000-BBBB"
    for d in (clean_run, leaky_run):
        d.mkdir(parents=True)
        (d / "meta.json").write_text("{}", encoding="utf-8")
    (leaky_run / "spans").mkdir()
    (leaky_run / "spans" / "x.txt").write_text("GEMINI_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrstuv", encoding="utf-8")

    assert contains_secret(leaky_run) and not contains_secret(clean_run)
    assert copy_run(leaky_run, tmp_dir / "results") is None
    assert copy_run(clean_run, tmp_dir / "results") == tmp_dir / "results" / clean_run.name
    with pytest.raises(FileExistsError):
        copy_run(clean_run, tmp_dir / "results")
    assert not (tmp_dir / "results" / leaky_run.name).exists()
