"""The read-only Phase 5 analyses reproduce their published figures from the committed run artifacts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from evaluation.phase5_analysis import broken_tests, error_trigger, flaky_runs, main

RESULTS = Path(__file__).resolve().parents[2] / "benchmark" / "results" / "phase5"


def test_req004_broken_tests_by_cause():
    rows = broken_tests(RESULTS)
    assert Counter(r["cause"] for r in rows) == {"error-area display": 10, "test code error: NameError": 7, "test code error: AttributeError": 3}
    assert Counter(r["trigger"] for r in rows if r["trigger"]) == {
        "unknown project id in the URL": 7, "empty title submitted": 2, "unknown user in the URL": 1}  # fmt: skip
    clean_false_positives = {r["n"] for r in rows if r["bugs"] == "clean" and r["surface"] == "DEFECT_FOUND"}
    assert clean_false_positives == {51, 69, 87}
    assert all(any(r["cause"] == "error-area display" for r in rows if r["n"] == n) for n in clean_false_positives)


def test_every_flaky_run_is_an_llm_retry():
    flaky = flaky_runs(RESULTS)
    assert [f["n"] for f in flaky] == [32, 34, 78, 88, 89]
    assert {r["parent"] for f in flaky for r in f["retried"]} == {"llm.chat"}
    assert all(f["underlying"] == "PASS" and all(r["succeeded_on_attempt"] for r in f["retried"]) for f in flaky)


def test_error_trigger_is_read_from_the_test_source():
    assert error_trigger('page.goto(f"{base_url}/?user=alice&project=99999")') == "unknown project id in the URL"
    assert error_trigger('page.get_by_test_id("new-title").fill("")') == "empty title submitted"
    assert error_trigger('page.goto(f"{base_url}/?user=nobody&project={pid}")') == "unknown user in the URL"


def test_cli_writes_only_into_the_analysis_folder(tmp_dir, monkeypatch):
    import shutil

    copy = tmp_dir / "phase5"
    shutil.copytree(RESULTS, copy, ignore=shutil.ignore_patterns("analysis", "spans", "prompts", "reports", "pytest", "tmp"))
    before = {p.relative_to(copy).as_posix(): p.stat().st_mtime_ns for p in copy.rglob("*") if p.is_file()}
    assert main(["--results-dir", str(copy)]) == 0
    after = {p.relative_to(copy).as_posix(): p.stat().st_mtime_ns for p in copy.rglob("*") if p.is_file()}
    assert {k for k in after if k not in before} == {"analysis/req004_breakdown.md", "analysis/flaky_causes.md", "analysis/timing_breakdown.md"}
    assert all(after[k] == v for k, v in before.items())  # no run file was rewritten
    assert "--baseline" not in (copy / "analysis" / "timing_breakdown.md").read_text(encoding="utf-8").splitlines()[2]
