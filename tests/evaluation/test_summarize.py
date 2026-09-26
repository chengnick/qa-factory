"""Rebuilding a summary from run directories: recomputes metrics, never touches run evidence."""

import json
from pathlib import Path

from evaluation.summarize import BEGIN, END, rebuild


def _meta(run_id, rnd, bugs, verdict, surface):
    return {"run_id": run_id, "round": rnd, "started_at": f"2026-09-25T16:0{rnd}:00+00:00", "requirement_id": "REQ-005", "sut_bugs": bugs,
            "verdict": verdict, "surface_verdict": surface, "differential": {"test_health": {"healthy": 3, "total": 3}},
            "trace_id": "t", "error": None}  # fmt: skip


def _results(tmp_dir: Path) -> Path:
    results = tmp_dir / "phase"
    for meta in (_meta("RUN-20260925-160100-AAAA", 1, ["B02"], "DEFECT_FOUND", "DEFECT_FOUND"), _meta("RUN-20260925-160200-BBBB", 2, [], "PASS", "PASS")):
        (results / meta["run_id"]).mkdir(parents=True)
        (results / meta["run_id"] / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    conditions = {"llm": "gemini", "model": "m", "models_seen": ["m"], "temperature": 0.0, "prompt_version": "v3",
                  "git_commit": {"sha": "abc", "dirty": True}, "lockfile_sha256": "h"}  # fmt: skip
    (results / "summary.json").write_text(json.dumps({"dataset": "dev", "rounds": 2, "conditions": conditions}), encoding="utf-8")
    (results / "acceptance.md").write_text(f"# Title\n\nintro\n\n{BEGIN}\nold table\n{END}\n\nhand-written notes\n", encoding="utf-8")
    return results


def test_rebuild_recomputes_metrics_and_keeps_run_conditions(tmp_dir):
    results = _results(tmp_dir)
    metas_before = {p: p.read_bytes() for p in results.glob("RUN-*/meta.json")}

    summary = rebuild(results)

    assert {p: p.read_bytes() for p in results.glob("RUN-*/meta.json")} == metas_before  # evidence untouched
    assert summary["conditions"]["git_commit"] == {"sha": "abc", "dirty": True}  # as recorded at run time
    assert summary["regenerated"]["runs_read"] == 2
    assert summary["metrics"]["true_detection_rate"]["pooled"] == "1/1"
    assert summary["metrics"]["true_detection_rate"]["ci95"] is not None
    assert [r["run_id"] for r in summary["runs"]] == ["RUN-20260925-160100-AAAA", "RUN-20260925-160200-BBBB"]
    assert "regenerated from the 2 run directories" in (results / "summary.md").read_text(encoding="utf-8")


def test_rebuild_replaces_only_the_marked_block_of_acceptance(tmp_dir):
    results = _results(tmp_dir)

    rebuild(results)

    text = (results / "acceptance.md").read_text(encoding="utf-8")
    assert text.startswith("# Title\n\nintro\n\n") and text.endswith("\n\nhand-written notes\n")
    assert "old table" not in text and "Wilson 95% CI" in text
