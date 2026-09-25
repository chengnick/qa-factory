"""Every run keeps its evidence in artifacts/{run_id}/ and nothing deletes it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import app
from tests.integration.test_pipeline_real_tools import API_FILE, UI_FILE, _script

REPO = Path(__file__).resolve().parents[2]
RUN_ID = re.compile(r"^RUN-\d{8}-\d{6}-[0-9A-F]{4}$")


def _run_dirs(base: Path) -> list[Path]:
    return sorted(p for p in base.iterdir() if p.is_dir())


def _meta(run_dir: Path) -> dict:
    return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))


def _trace(run_dir: Path) -> dict:
    return json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))


def _root(trace: dict) -> dict:
    (root,) = (s for s in trace["spans"] if s["parent_span_id"] is None)
    return root


def test_fake_run_writes_trace_and_run_record(tmp_dir):
    assert app.main(["--requirement", "REQ-005", "--llm", "fake", "--artifacts-dir", str(tmp_dir)]) == 0

    (run_dir,) = _run_dirs(tmp_dir)
    assert RUN_ID.match(run_dir.name)
    meta, trace = _meta(run_dir), _trace(run_dir)
    assert meta["run_id"] == run_dir.name
    assert meta["trace_id"] == trace["trace_id"] and meta["trace_file"] == "trace.json"
    assert meta["verdict"] == trace["run"]["verdict"] == "FLAKY"
    assert meta["prompt_version"] == "v3" and meta["dataset"] == "clean"
    assert set(meta["git_commit"]) == {"sha", "dirty"}
    assert "lockfile_sha256" in meta
    assert sorted(p.name for p in (run_dir / "prompts").iterdir())  # LLM inputs/outputs kept
    root = _root(trace)
    assert root["attributes"]["qa.run.id"] == run_dir.name  # run_id <-> trace_id both ways
    assert root["attributes"]["qa.run.prompt_version"] == "v3"
    assert root["attributes"]["qa.run.dataset"] == "clean"


def test_runs_accumulate_and_earlier_runs_are_untouched(tmp_dir):
    app.main(["--requirement", "REQ-005", "--llm", "fake", "--artifacts-dir", str(tmp_dir)])
    (first,) = _run_dirs(tmp_dir)
    before = {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}

    app.main(["--requirement", "REQ-005", "--llm", "fake", "--scenario", "pass", "--artifacts-dir", str(tmp_dir)])

    assert len(_run_dirs(tmp_dir)) == 2
    assert {p: p.read_bytes() for p in first.rglob("*") if p.is_file()} == before


def test_live_path_keeps_generated_tests_trace_and_junit(tmp_dir, monkeypatch):
    """The --llm gemini code path end to end, with the Gemini client replaced by a scripted LLM (offline)."""
    import llm.adapters.gemini as gemini

    monkeypatch.setattr(app, "ENV_FILE", tmp_dir / "no.env")
    monkeypatch.setattr(gemini, "GeminiClient", lambda model: _script([API_FILE, UI_FILE]))

    code = app.main(["--requirement", "REQ-005", "--llm", "gemini", "--sut-bugs", "", "--artifacts-dir", str(tmp_dir / "artifacts")])

    assert code == 0
    (run_dir,) = _run_dirs(tmp_dir / "artifacts")
    record = _meta(run_dir)
    assert record["verdict"] == "PASS" and record["sut_bugs"] == []
    assert record["generated_files"] == ["generated/test_req005_api.py", "generated/test_req005_ui.py"]
    assert (run_dir / "generated" / "test_req005_api.py").read_text(encoding="utf-8") == API_FILE["content"]
    assert len(list((run_dir / "reports").glob("junit-*.xml"))) == 2  # pytest + playwright
    assert _trace(run_dir)["trace_id"] == record["trace_id"]
    assert record["temperature"] == 0.0
    assert not list(tmp_dir.glob("*.json"))  # nothing written outside the run directory


@pytest.mark.parametrize("bugs", ["B01", "B02,B05", "b10"])
def test_sealed_test_set_bugs_are_refused_before_any_run(tmp_dir, bugs):
    with pytest.raises(SystemExit) as exc_info:
        app.main(["--requirement", "REQ-003", "--llm", "fake", "--sut-bugs", bugs, "--artifacts-dir", str(tmp_dir)])

    assert exc_info.value.code == 2
    assert not list(tmp_dir.iterdir())  # refused before a workspace or SUT exists


def test_dev_bug_run_is_labelled_dev(tmp_dir):
    assert app.main(["--requirement", "REQ-005", "--llm", "fake", "--sut-bugs", "B02", "--artifacts-dir", str(tmp_dir)]) == 0
    (run_dir,) = _run_dirs(tmp_dir)
    assert _meta(run_dir)["dataset"] == "dev"


DELETERS = re.compile(r"rmtree|\.unlink\(|os\.remove\(|\.rmdir\(|TemporaryDirectory|shutil\.move")


@pytest.mark.parametrize(
    "path",
    [REPO / "app.py", REPO / "pipeline.py", *sorted((REPO / "tools").glob("*.py")), *sorted((REPO / "observability").glob("*.py")),
     *sorted((REPO / "agents").glob("*.py")), *sorted((REPO / "evaluation").glob("*.py"))],
    ids=lambda p: p.relative_to(REPO).as_posix(),
)  # fmt: skip
def test_pipeline_code_never_deletes_files(path):
    assert not DELETERS.search(path.read_text(encoding="utf-8")), f"{path.name} deletes or moves files"
