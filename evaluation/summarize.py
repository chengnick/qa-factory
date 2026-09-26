"""Rebuild an evaluation summary from the run directories already on disk (no pipeline runs).

    python -m evaluation.summarize benchmark/results/phase2r

Reads every RUN-*/meta.json, recomputes the metrics with the current evaluation/metrics.py, rewrites
summary.json / summary.md, and refreshes the metrics block of acceptance.md between the markers
`<!-- metrics:begin -->` and `<!-- metrics:end -->`. Run directories and meta.json files are never modified.
The original run conditions (model, commit, lockfile) are kept; the regeneration itself is recorded.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.metrics import compute
from evaluation.provenance import git_commit
from evaluation.run import render_summary

BEGIN, END = "<!-- metrics:begin -->", "<!-- metrics:end -->"
RUN_FIELDS = ("round", "run_id", "trace_id", "requirement_id", "sut_bugs", "surface_verdict", "verdict", "differential", "error")


def load_runs(results_dir: Path) -> list[dict[str, Any]]:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(results_dir.glob("RUN-*/meta.json"))]
    return sorted(runs, key=lambda r: (r.get("round") or 0, r.get("started_at") or "", r["run_id"]))


def rebuild(results_dir: Path) -> dict[str, Any]:
    previous = json.loads((results_dir / "summary.json").read_text(encoding="utf-8"))
    runs = load_runs(results_dir)
    summary = {
        "dataset": previous["dataset"],
        "rounds": previous["rounds"],
        "conditions": previous["conditions"],  # conditions of the original runs, not of this regeneration
        "regenerated": {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": git_commit(), "runs_read": len(runs)},
        "metrics": compute(runs),
        "runs": [{**{k: r.get(k) for k in RUN_FIELDS}, "copied_to_results": True} for r in runs],
    }
    (results_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "summary.md").write_text(render_summary(summary), encoding="utf-8")
    acceptance = results_dir / "acceptance.md"
    if acceptance.is_file():
        text = acceptance.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            head, rest = text.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            acceptance.write_text(head + BEGIN + "\n" + render_metrics_zh(summary["metrics"]) + END + tail, encoding="utf-8")
    return summary


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _row(name: str, stat: dict[str, Any]) -> str:
    ci = stat.get("ci95")
    ci_text = f"{_pct(ci[0])}–{_pct(ci[1])}" if ci else "—"
    rng = f"{_pct(stat['min'])}–{_pct(stat['max'])}" if stat["mean"] is not None else "—"
    return f"| {name} | {_pct(stat['mean'])} | {rng} | {ci_text} | {stat['pooled']} | {stat['n_rounds']} |"


def render_metrics_zh(m: dict[str, Any]) -> str:
    """The metrics block of acceptance.md (Traditional Chinese), generated from summary metrics."""
    lines = [
        "| 指標 | 平均 | 範圍（每輪） | Wilson 95% CI（依合計） | 合計 | 輪數 n |",
        "|---|---|---|---|---|---|",
        _row("真實偵測率（交叉驗證）", m["true_detection_rate"]),
    ]
    if "true_detection_rate_completed" in m:
        lines.append(_row("偵測率（pipeline 完成時，排除 AGENT_FAILED）", m["true_detection_rate_completed"]))
    lines += [
        _row("表面偵測率（未交叉驗證）", m["surface_detection_rate"]),
        _row("**誤報率（surface，主要數字）**", m["false_positive_rate_surface"]),
        _row("誤報率（交叉驗證後；依定義為 0）", m["false_positive_rate_verified"]),
        _row("測試健康度（以測試為單位）", m["test_health"]),
        _row("環境阻擋率", m["env_blocked_rate"]),
        "",
        "- 平均與範圍以「每輪的比率」計算；95% 信賴區間是依全部 run 的合計計算的 Wilson 區間。",
        "- 環境阻擋（ENV_BLOCKED）的 run 不計入其他指標的分母；AGENT_FAILED 計入「真實偵測率」分母、視為未抓到。",
        "",
        "### 每個 bug 的偵測率",
        "",
    ]
    per_bug = m["per_bug_detection"]
    has_completed = any("completed" in v for v in per_bug.values())
    header = "| Bug | 交叉驗證 |" + (" pipeline 完成時 |" if has_completed else "") + " Surface | 環境阻擋 |"
    lines += [header, "|---|---|" + ("---|" if has_completed else "") + "---|---|"]
    for bug, v in per_bug.items():
        completed = f" {v['completed']} |" if has_completed else ""
        lines.append(f"| {bug} | {v['verified']} |{completed} {v['surface']} | {v['env_blocked']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m evaluation.summarize <results-dir>", file=sys.stderr)
        return 2
    summary = rebuild(Path(args[0]))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
