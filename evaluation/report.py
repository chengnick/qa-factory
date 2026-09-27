"""Final per-run report (spec v3 §12): report.json, built only from the files the run already wrote.

    python -m evaluation.report artifacts/RUN-... [more run dirs] --out DIR

The runner writes report.json as the last file of a run. The CLI rebuilds reports for existing runs into
--out (it never writes into the run directories, so committed results stay as they were).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ISOLATION_NOTES = {
    "L0+": "environment whitelist and per-run working directory; generated tests can still read and write local files",
    "L1": "in-process audit hook (tools/l1_guard.py): writes, network and processes limited; not an OS sandbox",
}


def _load(run_dir: Path, name: str) -> Any:
    path = run_dir / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def build_report(run_dir: Path) -> dict[str, Any]:
    meta = _load(run_dir, "meta.json") or {}
    classification = _load(run_dir, "classification.json") or {}
    differential = _load(run_dir, "differential.json")
    security = _load(run_dir, "security_events.json")
    workflow = _load(run_dir, "workflow_eval.json")
    spans = (_load(run_dir, "trace.json") or {}).get("spans", [])

    outcome = classification.get("final") or classification.get("surface") or {}
    attempts = [s for s in spans if s.get("name") == "attempt"]
    levels = sorted({s["attributes"]["qa.isolation.level"] for s in spans if "qa.isolation.level" in s.get("attributes", {})})
    counts = (differential or {}).get("counts") or {}
    commit = meta.get("git_commit")
    return {
        "run_id": meta.get("run_id", run_dir.name),
        "trace_id": meta.get("trace_id"),
        "meta": {
            "requirement_id": meta.get("requirement_id"),
            "model": meta.get("model"),
            "prompt_version": meta.get("prompt_version"),
            "dataset": meta.get("dataset"),
            "sut_bugs": meta.get("sut_bugs"),
            "git_commit": commit.get("sha") if isinstance(commit, dict) else commit,
            "git_dirty": commit.get("dirty") if isinstance(commit, dict) else None,
            "policy_hash": meta.get("policy_hash"),
            "conftest_sha256": meta.get("conftest_sha256"),
        },
        "verdict": meta.get("verdict"),
        "surface_verdict": meta.get("surface_verdict"),
        "underlying_verdict": meta.get("underlying_verdict"),
        "differential": None
        if differential is None
        else {"status": differential.get("status"), **{k: counts.get(k) for k in ("detected", "broken", "missed")}},
        "attribution": [
            {k: c.get(k) for k in ("span", "layer", "symptom", "matched_rule", "evidence", "test_id")}
            for c in outcome.get("classifications", [])
        ],
        "reliability": {
            "retries": sum(1 for s in attempts if s.get("attributes", {}).get("qa.retry.attempt", 1) > 1),
            "flaky": bool(outcome.get("flaky")),
        },
        "security": None
        if security is None
        else {"events": len(security.get("events", [])), "breach": bool(security.get("breach"))},
        "workflow": None
        if workflow is None
        else {k: workflow.get(k) for k in ("workflow_status", "violations", "goal_drift", "rounds")},
        "isolation_level": "+".join(levels) if levels else None,
        "isolation_note": "; ".join(ISOLATION_NOTES.get(level, level) for level in levels) or None,
        "artifacts_complete": None if workflow is None or "missing_evidence" not in workflow else not workflow["missing_evidence"],
        "missing_evidence": None if workflow is None else workflow.get("missing_evidence"),
    }


def write_report(run_dir: Path, out: Path | None = None) -> Path:
    target = (out or run_dir) / ("report.json" if out is None else f"{run_dir.name}.report.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_report(run_dir), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild report.json for existing runs into another directory.")
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="where to write <run_id>.report.json (never the run dirs)")
    args = parser.parse_args(argv)
    for run_dir in args.runs:
        if not (run_dir / "meta.json").is_file():
            print(f"skip {run_dir}: no meta.json", file=sys.stderr)
            continue
        print(write_report(run_dir, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
