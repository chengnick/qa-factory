"""Re-classify recorded runs offline with the current rule table (no pipeline, no LLM, no SUT).

    python -m evaluation.classify_runs <results-dir> [--out benchmark/results/phase3]

For each RUN-*/ it reads trace.json, differential.json and the junit reports, rebuilds the surface and
the final (cross-validated) verdicts, and compares them with the verdicts recorded at run time. Traces
written before Phase 3 carry no per-test events; those results are taken from the QA run's junit reports
(the ones not listed as cross-validation build reports in differential.json). Run directories are only read.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from classification.observations import observe
from classification.verdict import final_outcome, surface_outcome
from tools.pytest_tool import junit_tests

RUNNERS = ("tool.pytest", "tool.playwright")


def _qa_junit_results(run_dir: Path, spans: list[dict[str, Any]], differential: dict[str, Any] | None) -> dict[str, list[dict[str, str]]]:
    build_reports = {r.get("junit") for b in (differential or {}).get("builds", []) for r in b.get("runs", [])}
    qa_reports = sorted(p for p in (run_dir / "reports").glob("junit-*.xml") if p.relative_to(run_dir).as_posix() not in build_reports)
    fallback: dict[str, list[dict[str, str]]] = {}
    for span in spans:
        if span["name"] not in RUNNERS or any(e["name"] == "qa.test.result" for e in span.get("events", [])):
            continue
        files = str(span["attributes"].get("qa.tool.command", "")).split()[1:]
        stems = {Path(f).stem for f in files}
        for report in qa_reports:
            stem = report.stem.removeprefix("junit-").rsplit("-", 1)[0]
            if stem in stems:
                fallback[span["span_id"]] = junit_tests(report, run_dir)
                break
    return fallback


def classify_run(run_dir: Path) -> dict[str, Any]:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    trace_file = run_dir / "trace.json"
    spans = json.loads(trace_file.read_text(encoding="utf-8"))["spans"] if trace_file.is_file() else []
    diff_file = run_dir / "differential.json"
    differential = json.loads(diff_file.read_text(encoding="utf-8")) if diff_file.is_file() else None
    obs = observe(spans, differential=differential, test_results_fallback=_qa_junit_results(run_dir, spans, differential))
    surface = surface_outcome(obs)
    final = final_outcome(obs, bugs_enabled=bool(meta.get("sut_bugs"))) if differential is not None else surface
    return {
        "run_id": meta["run_id"],
        "round": meta.get("round"),
        "requirement_id": meta.get("requirement_id"),
        "sut_bugs": meta.get("sut_bugs", []),
        "recorded": {"surface": meta.get("surface_verdict"), "final": meta.get("verdict")},
        "reclassified": {"surface": surface.verdict, "final": final.verdict, "underlying": final.underlying_verdict},
        "surface": surface.to_json(),
        "final": final.to_json(),
    }


def distribution(runs: list[dict[str, Any]], which: str) -> dict[str, dict[str, int]]:
    classifications = [c for r in runs for c in r[which]["classifications"]]
    return {
        "layer": dict(Counter(c["layer"] for c in classifications)),
        "symptom": dict(Counter(c["symptom"] for c in classifications)),
        "rule": dict(Counter(c["matched_rule"] or "UNKNOWN" for c in classifications)),
        "layer_symptom_rule": dict(Counter(f"{c['layer']}/{c['symptom']}/{c['matched_rule'] or 'UNKNOWN'}" for c in classifications)),
        "verdict": dict(Counter(r["reclassified"]["surface" if which == "surface" else "final"] for r in runs)),
    }


def mismatches(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for r in runs:
        for which in ("surface", "final"):
            before, after = r["recorded"][which], r["reclassified"][which]
            if before != after:
                decided = r[which]["decided_by"] or {}
                rows.append({"run_id": r["run_id"], "which": which, "recorded": before, "reclassified": after,
                             "rule": decided.get("matched_rule"), "evidence": decided.get("evidence", "")})  # fmt: skip
    return rows


def render(summary: dict[str, Any]) -> str:
    def table(title: str, counts: dict[str, int]) -> list[str]:
        lines = [f"**{title}**", "", "| Value | Count |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        return lines + [""]

    lines = [f"# Re-classification of `{summary['source']}` ({summary['runs']} runs)", "",
             "Offline, current rule table; run directories were only read.", ""]  # fmt: skip
    for which, label in (("final", "Final (cross-validated) classifications"), ("surface", "Surface (pipeline-only) classifications")):
        d = summary["distribution"][which]
        lines += [f"## {label}", ""]
        lines += table("Verdicts", d["verdict"]) + table("Layer / symptom / rule", d["layer_symptom_rule"])
    lines += ["## Verdicts that differ from the ones recorded at run time", ""]
    if not summary["mismatches"]:
        lines.append("None.")
    else:
        lines += ["| run_id | Which | Recorded | Re-classified | Rule | Evidence |", "|---|---|---|---|---|---|"]
        for m in summary["mismatches"]:
            evidence = m["evidence"][:140].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{m['run_id']}` | {m['which']} | {m['recorded']} | {m['reclassified']} | {m['rule']} | {evidence} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = [classify_run(d) for d in sorted(args.results_dir.glob("RUN-*")) if (d / "meta.json").is_file()]
    summary = {
        "source": args.results_dir.as_posix(),
        "runs": len(runs),
        "distribution": {"final": distribution(runs, "final"), "surface": distribution(runs, "surface")},
        "mismatches": mismatches(runs),
        "per_run": runs,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    name = f"{args.results_dir.name}_classification"
    (args.out / f"{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / f"{name}.md").write_text(render(summary), encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
