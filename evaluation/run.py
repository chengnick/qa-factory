"""Multi-round evaluation runner (spec v3 §11.1, Phase 2R).

    python -m evaluation.run --dataset dev --rounds 5 --llm gemini --model gemini-3.5-flash-lite

Each run: a fresh SUT with the combination's bugs, the full pipeline (real tools), then cross-validation
of the final tests on a fresh bug SUT and a fresh clean SUT (evaluation/differential.py). Every run's
artifacts/{run_id}/ is copied to the results directory; nothing is deleted.

Guards: --llm gemini refuses a dirty git worktree (results must map to a commit); --dataset test refuses
to run while benchmark/frozen.yaml does not exist (spec v3 §3.3). Provider errors are recorded as they
happen (ENV_BLOCKED); runs are never retried with another model.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.contracts import RequirementInput
from agents.version import PROMPT_VERSION
from benchmark.datasets import DEV_COMBINATIONS, dataset_of
from evaluation.differential import SutFactory, run_differential
from evaluation.metrics import compute
from evaluation.provenance import git_commit, lockfile_sha256
from llm.client import LLMClient
from observability.clock import Clock, SystemClock
from observability.instrument import Instrumentation, RunContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.redact import find_secret
from observability.setup import create_tracer_provider, get_tracer
from pipeline import run_pipeline
from sut.launcher import SUTStartupError, running_sut
from tools.factory import real_tools
from tools.registry import NO_RETRY, RetryPolicy
from tools.workspace import create_run_workspace, new_run_id

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = REPO_ROOT / "benchmark" / "requirements"
API_REFERENCE = REPO_ROOT / "docs" / "sut-api.md"
FROZEN = REPO_ROOT / "benchmark" / "frozen.yaml"


class RunnerRefused(RuntimeError):
    """A guard refused to start the evaluation."""


# --------------------------------------------------------------------------- one run


@contextlib.contextmanager
def instrumentation(workspace: Path, clock: Clock) -> Iterator[Instrumentation]:
    """Trace -> {workspace}/trace.json; full-size content -> {workspace}/prompts/ and spans/."""
    provider = create_tracer_provider(JsonFileSpanExporter(workspace, filename="trace.json"))
    try:
        yield Instrumentation(get_tracer(provider), clock, RunContentSink(workspace))
    finally:
        provider.shutdown()


def base_meta(run_id: str, requirement_id: str, *, llm: str, model: str, temperature: float | None, sut_bugs: Sequence[str]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "trace_id": None,
        "trace_file": None,
        "requirement_id": requirement_id,
        "llm": llm,
        "model": model,
        "temperature": temperature,
        "prompt_version": PROMPT_VERSION,
        "dataset": dataset_of(sut_bugs),
        "sut_bugs": list(sut_bugs),
        "git_commit": git_commit(),
        "lockfile_sha256": lockfile_sha256(),
        "started_at": _now(),
    }


def write_meta(workspace: Path, meta: dict[str, Any]) -> None:
    (workspace / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trace_facts(workspace: Path) -> dict[str, Any]:
    """Model versions actually reported by the provider and token totals, read back from trace.json."""
    trace_file = workspace / "trace.json"
    if not trace_file.is_file():
        return {"models_seen": [], "tokens": {"input": None, "output": None, "total": None}}
    spans = json.loads(trace_file.read_text(encoding="utf-8"))["spans"]
    llm = [s["attributes"] for s in spans if s["name"] == "llm.chat"]
    models = sorted({a["gen_ai.response.model"] for a in llm if "gen_ai.response.model" in a})
    ins = [a["gen_ai.usage.input_tokens"] for a in llm if "gen_ai.usage.input_tokens" in a]
    outs = [a["gen_ai.usage.output_tokens"] for a in llm if "gen_ai.usage.output_tokens" in a]
    total = (sum(ins) + sum(outs)) if (ins or outs) else None
    return {"models_seen": models, "tokens": {"input": sum(ins) if ins else None, "output": sum(outs) if outs else None, "total": total}}


def execute_run(
    *,
    requirement_id: str,
    sut_bugs: Sequence[str],
    llm: LLMClient,
    llm_kind: str,
    model: str,
    artifacts_dir: Path,
    temperature: float | None = None,
    llm_retry: RetryPolicy = NO_RETRY,
    differential: bool = True,
    sut_factory: SutFactory = running_sut,
    sut_url: str | None = None,
    round_no: int | None = None,
    clock: Clock | None = None,
) -> tuple[Path, dict[str, Any]]:
    """One live run with real tools. Returns (workspace, meta). meta.json is always written."""
    run_id = new_run_id()
    workspace = create_run_workspace(artifacts_dir, run_id)
    meta = base_meta(run_id, requirement_id, llm=llm_kind, model=model, temperature=temperature, sut_bugs=sut_bugs)
    meta.update(round=round_no, sut_url=sut_url, evaluation_mode=differential)
    requirement = RequirementInput(requirement_id, (REQUIREMENTS_DIR / f"{requirement_id}.md").read_text(encoding="utf-8"))
    started = time.monotonic()
    sut = contextlib.nullcontext(sut_url) if sut_url else sut_factory(sut_bugs)
    try:
        with sut as url, instrumentation(workspace, clock or SystemClock()) as inst:
            cross_validate = (lambda automation: run_differential(workspace, automation, sut_bugs, inst, sut_factory)) if differential else None
            result = run_pipeline(
                requirement,
                llm=llm,
                tools=real_tools(workspace, url),
                inst=inst,
                sut_bugs=sut_bugs,
                llm_retry=llm_retry,
                api_reference=API_REFERENCE.read_text(encoding="utf-8"),
                run_id=run_id,
                dataset=meta["dataset"],
                differential=cross_validate,
            )
    except SUTStartupError as exc:
        meta.update(verdict="ENV_BLOCKED", surface_verdict="ENV_BLOCKED", error=f"SUTStartupError: {exc}", finished_at=_now())
        write_meta(workspace, meta)
        return workspace, meta
    except Exception as exc:  # unclassified: keep the evidence, then crash loudly
        meta.update(error=f"{type(exc).__name__}: {exc}", finished_at=_now(), duration_s=round(time.monotonic() - started, 1))
        write_meta(workspace, meta)
        raise
    diff = result.differential
    meta.update(
        trace_id=result.trace_id,
        trace_file="trace.json",
        verdict=result.verdict,
        surface_verdict=result.surface_verdict,
        error=result.error,
        differential=None
        if diff is None
        else {"status": diff.status, "verdict": diff.verdict, "reason": diff.reason, "counts": diff.counts, "test_health": diff.test_health},
        generated_files=sorted(p.relative_to(workspace).as_posix() for p in (workspace / "generated").glob("test_*.py")),
        finished_at=_now(),
        duration_s=round(time.monotonic() - started, 1),
        **_trace_facts(workspace),
    )
    write_meta(workspace, meta)
    return workspace, meta


# --------------------------------------------------------------------------- dataset


def combinations(dataset: str) -> list[tuple[str, list[str]]]:
    if dataset == "dev":
        bugged = [(req, [bug]) for req, bug in DEV_COMBINATIONS]
        clean = [(req, []) for req, _ in DEV_COMBINATIONS]
        return bugged + clean
    if dataset == "test":
        if not FROZEN.is_file():
            raise RunnerRefused(f"{FROZEN} does not exist (benchmark/frozen.yaml): the test set stays sealed (spec v3 §3.3)")
        raise RunnerRefused("test-set evaluation is Phase 5 and not implemented yet")
    raise RunnerRefused(f"unknown dataset {dataset!r}")


def contains_secret(path: Path) -> bool:
    """Any credential-shaped string in any file of the run (observability.redact.SECRET_SHAPES)."""
    return any(f.is_file() and find_secret(f.read_text(encoding="utf-8", errors="replace")) for f in path.rglob("*"))


def copy_run(workspace: Path, results_dir: Path) -> Path | None:
    """Copy one run into the results directory. Refuses to overwrite; skips (returns None) on a secret match."""
    target = results_dir / workspace.name
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    if contains_secret(workspace):
        return None
    results_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace, target)
    return target


def run_dataset(
    *,
    dataset: str,
    rounds: int,
    llm_factory: Callable[[], LLMClient],
    llm_kind: str,
    model: str,
    artifacts_dir: Path,
    results_dir: Path,
    temperature: float | None = None,
    llm_retry: RetryPolicy = NO_RETRY,
    pause_s: float = 0.0,
    only: Sequence[tuple[str, list[str]]] | None = None,
    sut_factory: SutFactory = running_sut,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    plan = list(only) if only is not None else combinations(dataset)
    if (results_dir / "summary.json").exists():
        raise RunnerRefused(f"{results_dir / 'summary.json'} already exists; results are never overwritten")
    runs: list[dict[str, Any]] = []
    first = True
    for rnd in range(1, rounds + 1):
        for requirement_id, bugs in plan:  # interleaved: every combination once per round
            if not first and pause_s:
                sleep(pause_s)
            first = False
            workspace, meta = execute_run(
                requirement_id=requirement_id,
                sut_bugs=bugs,
                llm=llm_factory(),
                llm_kind=llm_kind,
                model=model,
                artifacts_dir=artifacts_dir,
                temperature=temperature,
                llm_retry=llm_retry,
                sut_factory=sut_factory,
                round_no=rnd,
            )
            copied = copy_run(workspace, results_dir)
            meta["copied_to_results"] = copied is not None
            if copied is None:
                meta["copy_skipped_reason"] = "secret-like string found; run kept only under artifacts/"
            runs.append(meta)
            log(f"round {rnd} {requirement_id} {bugs or '[]'} -> {meta.get('verdict')} (surface {meta.get('surface_verdict')}) {meta['run_id']}")
    summary = {
        "dataset": dataset,
        "rounds": rounds,
        "conditions": {
            "llm": llm_kind,
            "model": model,
            "models_seen": sorted({m for r in runs for m in r.get("models_seen", [])}),
            "temperature": temperature,
            "prompt_version": PROMPT_VERSION,
            "git_commit": git_commit(),
            "lockfile_sha256": lockfile_sha256(),
        },
        "metrics": compute(runs),
        "runs": [
            {k: r.get(k) for k in ("round", "run_id", "trace_id", "requirement_id", "sut_bugs", "surface_verdict", "verdict", "differential", "error", "copied_to_results")}
            for r in runs
        ],
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "summary.md").write_text(render_summary(summary), encoding="utf-8")
    return summary


# --------------------------------------------------------------------------- report


def _fmt_rate(stat: dict[str, Any]) -> str:
    if stat["mean"] is None:
        return f"n/a (pooled {stat['pooled']})"
    ci = stat.get("ci95")
    ci_text = f", 95% CI {ci[0]:.0%}–{ci[1]:.0%}" if ci else ""
    return f"{stat['mean']:.0%} (range {stat['min']:.0%}–{stat['max']:.0%}, rounds n={stat['n_rounds']}; pooled {stat['pooled']}{ci_text})"


def render_summary(summary: dict[str, Any]) -> str:
    m, c = summary["metrics"], summary["conditions"]
    lines = [
        f"# Evaluation summary: dataset `{summary['dataset']}`, {summary['rounds']} rounds",
        "",
        f"- Model: `{c['model']}` (reported by provider: {', '.join(c['models_seen']) or 'n/a'}), temperature {c['temperature']}",
        f"- Prompt version: `{c['prompt_version']}`; git commit `{c['git_commit']['sha']}` (dirty: {c['git_commit']['dirty']}); lockfile sha256 `{c['lockfile_sha256']}`",
        *(
            [f"- Summary regenerated from the {summary['regenerated']['runs_read']} run directories on {summary['regenerated']['at']} "
             f"(commit `{summary['regenerated']['git_commit']['sha']}`); no pipeline was re-run."]
            if summary.get("regenerated") else []
        ),
        "",
        "## Metrics (spec v3 §11.2)",
        "",
        "Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| True detection rate (cross-validated) | {_fmt_rate(m['true_detection_rate'])} |",
        f"| Surface detection rate (unverified) | {_fmt_rate(m['surface_detection_rate'])} |",
        f"| **False-positive rate (surface, main figure)** | {_fmt_rate(m['false_positive_rate_surface'])} |",
        f"| False-positive rate (cross-validated; 0 by construction) | {_fmt_rate(m['false_positive_rate_verified'])} |",
        f"| Test health | {_fmt_rate(m['test_health'])} |",
        f"| Environment-block rate | {_fmt_rate(m['env_blocked_rate'])} |",
        "",
        "## Per-bug detection",
        "",
        "| Bug | Cross-validated | Surface | ENV_BLOCKED |",
        "|---|---|---|---|",
        *[f"| {bug} | {v['verified']} | {v['surface']} | {v['env_blocked']} |" for bug, v in m["per_bug_detection"].items()],
        "",
        f"Cost: mean tokens {m['cost']['mean_tokens']}, mean duration {m['cost']['mean_duration_s']} s, n={m['cost']['n']}",
        "",
        "## Runs",
        "",
        "| Round | run_id | Requirement | Bugs | Surface | Verdict | Cross-validation | detected / broken / tests | Note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["runs"]:
        d = r.get("differential") or {}
        counts = d.get("counts") or {}
        cv = f"{d.get('status')}" if d else "not run"
        tally = f"{counts.get('detected', '-')} / {counts.get('broken', '-')} / {counts.get('tests', '-')}" if counts else "-"
        note = (r.get("error") or d.get("reason") or "")[:120].replace("|", "\\|")
        if not r.get("copied_to_results"):
            note = ("NOT COPIED; " + note).strip()
        bugs = ",".join(r["sut_bugs"]) or "(clean)"
        lines.append(f"| {r['round']} | `{r['run_id']}` | {r['requirement_id']} | {bugs} | {r['surface_verdict']} | {r['verdict']} | {cv} | {tally} | {note} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def require_clean_worktree() -> None:
    commit = git_commit()
    if commit["sha"] is None:
        raise RunnerRefused("not a git checkout; live evaluation results must map to a commit")
    if commit["dirty"]:
        raise RunnerRefused("git worktree is dirty; commit or stash first so results map to an exact commit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, choices=["dev", "test"])
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--llm", choices=["gemini", "fake"], required=True)
    parser.add_argument("--model", help="gemini model id (required for --llm gemini; fixed for the whole evaluation)")
    parser.add_argument("--pause-s", type=float, default=10.0, help="pause between runs (free-tier pacing)")
    parser.add_argument("--artifacts-dir", type=Path, default=REPO_ROOT / "artifacts")
    parser.add_argument("--results-dir", type=Path, required=True, help="e.g. benchmark/results/phase2r")
    args = parser.parse_args(argv)

    try:
        combinations(args.dataset)
        if args.llm == "gemini":
            if not args.model:
                parser.error("--model is required with --llm gemini")
            require_clean_worktree()
            from app import ENV_FILE, load_env_file
            from llm.adapters.gemini import GEMINI_RETRY, GeminiClient

            load_env_file(ENV_FILE)
            GeminiClient(args.model)  # fail fast on a missing key, before any SUT starts
            factory, retry, temperature, model = (lambda: GeminiClient(args.model)), GEMINI_RETRY, 0.0, args.model
        else:
            from testing.scripts import dry_run_llm

            factory, retry, temperature, model = dry_run_llm, NO_RETRY, None, "fake-model"
    except RunnerRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        summary = run_dataset(
            dataset=args.dataset,
            rounds=args.rounds,
            llm_factory=factory,
            llm_kind=args.llm,
            model=model,
            artifacts_dir=args.artifacts_dir,
            results_dir=args.results_dir,
            temperature=temperature,
            llm_retry=retry,
            pause_s=args.pause_s if args.llm == "gemini" else 0.0,
        )
    except RunnerRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(render_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
