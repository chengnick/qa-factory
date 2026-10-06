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
from benchmark.datasets import DEV_COMBINATIONS, DEV_REQUIREMENTS, TEST_CLEAN_REQUIREMENTS, TEST_COMBINATIONS, dataset_of, set_of
from evaluation import workflow as wf
from evaluation.differential import SutFactory, run_differential
from evaluation.metrics import compute
from evaluation.provenance import conftest_sha256, git_commit, lockfile_sha256
from evaluation.report import write_report
from llm.client import LLMClient
from observability.clock import Clock, SystemClock
from observability.instrument import Instrumentation, RunContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.redact import find_secret, redact
from observability.setup import new_instrumentation
from permissions.policy import DEFAULT_POLICY_PATH, Policy, PolicyError, default_policy, load_policy
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
    provider, inst = new_instrumentation(clock, RunContentSink(workspace), JsonFileSpanExporter(workspace, filename="trace.json"))
    try:
        yield inst
    finally:
        provider.shutdown()


def base_meta(
    run_id: str, requirement_id: str, *, llm: str, model: str, temperature: float | None, sut_bugs: Sequence[str], policy: Policy | None = None
) -> dict[str, Any]:
    policy = policy or default_policy()
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
        "conftest_sha256": conftest_sha256(),
        "policy_hash": policy.hash,
        "policy_path": policy.display_path,
        "started_at": _now(),
    }


def write_meta(workspace: Path, meta: dict[str, Any]) -> None:
    (workspace / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def record_rounds(workspace: Path, meta: dict[str, Any], rounds: list[dict[str, Any]]) -> None:
    """rounds.json: per revision round, the snapshotted files (generated/roundN/) and the test results."""
    (workspace / "rounds.json").write_text(json.dumps({"rounds": rounds}, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["revision_rounds"] = len(rounds)


def record_workflow(workspace: Path, meta: dict[str, Any], workflow: dict[str, Any] | None) -> None:
    """W05 (evidence complete) once every other file is written, then workflow_eval.json (spec v3 §9.4).

    W01-W04 came from the pipeline. A W05 violation is appended to security_events.json as WORKFLOW_VIOLATION
    (span_id null: the trace is already closed). Rewrites meta.json with the workflow summary.
    """
    if workflow is None:
        return
    missing, w05 = wf.evaluate_evidence(workspace, meta)
    events_file = workspace / "security_events.json"
    if w05 and events_file.is_file():
        security = json.loads(events_file.read_text(encoding="utf-8"))
        security["events"] += [
            {"type": "WORKFLOW_VIOLATION", "run_id": meta["run_id"], "span_id": None, "agent": None, "action": "W05",
             "target": v.evidence.removeprefix("missing: "), "executed": False, "evidence": v.evidence}  # fmt: skip
            for v in w05
        ]
        record_security(workspace, meta, security)
    result = dict(workflow)
    result["violations"] = workflow["violations"] + [v.to_json() for v in w05]
    result["workflow_status"] = "FAIL" if result["violations"] else "PASS"
    result["rules_checked"] = ["W01", "W02", "W03", "W04", "W05"]
    result["acceptance_mode"] = meta.get("evaluation_mode") is True
    result["missing_evidence"] = missing
    (workspace / "workflow_eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["workflow"] = {"status": result["workflow_status"], "goal_drift": result["goal_drift"],
                        "violations": [v["rule"] for v in result["violations"]], "missing_evidence": len(missing)}  # fmt: skip
    write_meta(workspace, meta)
    write_report(workspace)  # last: report.json summarises every other file (spec v3 §12)


def record_policy(meta: dict[str, Any], policy: dict[str, Any] | None) -> None:
    """Permission-check statistics go to meta.json only (security_events.json holds security events)."""
    if policy is not None:
        meta["permission_checks"] = {k: policy[k] for k in ("permission_checks", "allowed", "denied")}


def record_security(workspace: Path, meta: dict[str, Any], security: dict[str, Any] | None) -> None:
    """security_events.json (spec v3 §7); a breach (any executed event) is flagged in meta."""
    if security is None:
        return
    (workspace / "security_events.json").write_text(json.dumps(security, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["security"] = {"events": len(security["events"]), "breach": security["breach"], "types": sorted({e["type"] for e in security["events"]})}


def record_classification(workspace: Path, meta: dict[str, Any], classification: dict[str, Any] | None, underlying: str | None) -> None:
    """Write classification.json and copy its headline numbers into meta (spec v3 §5)."""
    if classification is None:
        return
    (workspace / "classification.json").write_text(json.dumps(classification, ensure_ascii=False, indent=2), encoding="utf-8")
    decisive = classification.get("final") or classification["surface"]
    meta["underlying_verdict"] = underlying
    meta["classification"] = {
        "counts": decisive["counts"],
        "surface_counts": classification["surface"]["counts"],
        "decided_by": decisive["decided_by"],
        "flaky": decisive["flaky"],
    }


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
    policy: Policy | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """One live run with real tools. Returns (workspace, meta). meta.json is always written."""
    policy = policy or default_policy()
    run_id = new_run_id()
    workspace = create_run_workspace(artifacts_dir, run_id)
    meta = base_meta(run_id, requirement_id, llm=llm_kind, model=model, temperature=temperature, sut_bugs=sut_bugs, policy=policy)
    meta.update(round=round_no, sut_url=sut_url, evaluation_mode=differential, **(extra_meta or {}))
    requirement = RequirementInput(requirement_id, (REQUIREMENTS_DIR / f"{requirement_id}.md").read_text(encoding="utf-8"))
    started = time.monotonic()
    sut = contextlib.nullcontext(sut_url) if sut_url else sut_factory(sut_bugs)
    try:
        with sut as url, instrumentation(workspace, clock or SystemClock()) as inst:
            cross_validate = (lambda automation: run_differential(workspace, automation, sut_bugs, inst, sut_factory)) if differential else None
            result = run_pipeline(
                requirement,
                llm=llm,
                tools=real_tools(workspace, url, policy),
                inst=inst,
                sut_bugs=sut_bugs,
                llm_retry=llm_retry,
                api_reference=API_REFERENCE.read_text(encoding="utf-8"),
                run_id=run_id,
                dataset=meta["dataset"],
                differential=cross_validate,
                policy=policy,
                workspace=workspace,
                sut_url=url,
            )
    except SUTStartupError as exc:
        meta.update(verdict="ENV_BLOCKED", surface_verdict="ENV_BLOCKED", error=redact(f"SUTStartupError: {exc}"), finished_at=_now())
        write_meta(workspace, meta)
        return workspace, meta
    except Exception as exc:  # unclassified: keep the evidence, then crash loudly
        meta.update(error=redact(f"{type(exc).__name__}: {exc}"), finished_at=_now(), duration_s=round(time.monotonic() - started, 1))
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
    record_classification(workspace, meta, result.classification, result.underlying_verdict)
    record_security(workspace, meta, result.security)
    record_policy(meta, result.policy)
    record_rounds(workspace, meta, result.rounds)
    write_meta(workspace, meta)
    record_workflow(workspace, meta, result.workflow)
    return workspace, meta


# --------------------------------------------------------------------------- dataset


DATASETS = ("dev", "test", "phase5")


def combinations(dataset: str) -> list[tuple[str, list[str]]]:
    """dev: the 3 dev bugs + their clean runs. test: the 7 held-out bugs + the clean runs of the test requirements.
    phase5: both (18 combinations). test and phase5 need benchmark/frozen.yaml (spec v3 §3.3)."""
    dev = [(req, [bug]) for req, bug in DEV_COMBINATIONS] + [(req, []) for req in DEV_REQUIREMENTS]
    if dataset == "dev":
        return dev
    if dataset in ("test", "phase5"):
        if not FROZEN.is_file():
            raise RunnerRefused(f"{FROZEN} does not exist (benchmark/frozen.yaml): the test set stays sealed (spec v3 §3.3)")
        test = [(req, [bug]) for req, bug in TEST_COMBINATIONS] + [(req, []) for req in TEST_CLEAN_REQUIREMENTS]
        return test if dataset == "test" else dev + test
    raise RunnerRefused(f"unknown dataset {dataset!r}")


def check_frozen(model: str, policy: Policy | None = None, path: Path | None = None) -> str:
    """Refuse unless every frozen condition matches the current checkout; returns the freeze file's sha256."""
    from evaluation import frozen

    path = path or FROZEN
    doc = frozen.load(path)
    if doc is None:
        raise RunnerRefused(f"{path} does not exist: the test set stays sealed (spec v3 §3.3)")
    problems = frozen.mismatches(doc, frozen.current_conditions(model, policy))
    if problems:
        raise RunnerRefused("conditions differ from benchmark/frozen.yaml, test-set results would be contaminated: " + "; ".join(problems))
    return frozen.file_sha256(path)


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
    policy: Policy | None = None,
    frozen_sha256: str | None = None,
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
                policy=policy,
                extra_meta={"set": set_of(requirement_id, bugs), **({"frozen_sha256": frozen_sha256} if frozen_sha256 else {})},
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
            **({"frozen_sha256": frozen_sha256} if frozen_sha256 else {}),
        },
        "metrics": compute(runs),
        **(
            {"metrics_by_set": {name: compute([r for r in runs if r.get("set") == name]) for name in ("dev", "test")
                                if any(r.get("set") == name for r in runs)}}  # fmt: skip
            if len({r.get("set") for r in runs}) > 1
            else {}
        ),
        "runs": [
            {k: r.get(k) for k in ("round", "set", "run_id", "trace_id", "requirement_id", "sut_bugs", "surface_verdict", "verdict", "differential", "error", "copied_to_results")}
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


SET_TITLES = {"dev": "Dev set (B02-B04; used for prompt tuning)", "test": "Test set (held out; first run after the freeze)"}


def _metric_lines(m: dict[str, Any], title: str) -> list[str]:
    return [
        "",
        f"## {title}",
        "",
        "Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| True detection rate (cross-validated) | {_fmt_rate(m['true_detection_rate'])} |",
        f"| Detection rate when the pipeline completed (AGENT_FAILED and R20 excluded) | {_fmt_rate(m['true_detection_rate_completed'])} |",
        f"| Surface detection rate (unverified) | {_fmt_rate(m['surface_detection_rate'])} |",
        f"| **False-positive rate (surface, main figure)** | {_fmt_rate(m['false_positive_rate_surface'])} |",
        f"| False-positive rate (cross-validated; 0 by construction) | {_fmt_rate(m['false_positive_rate_verified'])} |",
        f"| Test health | {_fmt_rate(m['test_health'])} |",
        f"| Environment-block rate | {_fmt_rate(m['env_blocked_rate'])} |",
        *(
            [
                f"| INCONCLUSIVE rate (no rule matched a failure) | {_fmt_rate(m['inconclusive_rate'])} |",
                f"| UNKNOWN classification rate | {m['unknown_classification_rate']['pooled']} classifications "
                f"({m['unknown_classification_rate']['runs_with_classification']} runs with classification) |",
            ]
            if "inconclusive_rate" in m
            else []
        ),
        "",
        "### Per-bug detection",
        "",
        "| Bug | Cross-validated | Pipeline completed | AGENT_FAILED | R20 (LLM request rejected) | Surface | ENV_BLOCKED |",
        "|---|---|---|---|---|---|---|",
        *[
            f"| {bug} | {v['verified']} | {v['completed']} | {v['agent_failed']} | {v.get('llm_rejected', '0/0')} | {v['surface']} | {v['env_blocked']} |"
            for bug, v in m["per_bug_detection"].items()
        ],
        "",
        f"Cost: mean tokens {m['cost']['mean_tokens']}, mean duration {m['cost']['mean_duration_s']} s, n={m['cost']['n']}",
    ]


def render_summary(summary: dict[str, Any]) -> str:
    c = summary["conditions"]
    lines = [
        f"# Evaluation summary: dataset `{summary['dataset']}`, {summary['rounds']} rounds",
        "",
        f"- Model: `{c['model']}` (reported by provider: {', '.join(c['models_seen']) or 'n/a'}), temperature {c['temperature']}",
        f"- Prompt version: `{c['prompt_version']}`; git commit `{c['git_commit']['sha']}` (dirty: {c['git_commit']['dirty']}); lockfile sha256 `{c['lockfile_sha256']}`",
        *([f"- Frozen conditions: `benchmark/frozen.yaml` sha256 `{c['frozen_sha256']}`, every field matched"] if c.get("frozen_sha256") else []),
        *(
            [f"- Summary regenerated from the {summary['regenerated']['runs_read']} run directories on {summary['regenerated']['at']} "
             f"(commit `{summary['regenerated']['git_commit']['sha']}`); no pipeline was re-run."]
            if summary.get("regenerated") else []
        ),
        *(
            _metric_lines(summary["metrics"], "Metrics (spec v3 §11.2)")
            if "metrics_by_set" not in summary
            else [line for name, sm in summary["metrics_by_set"].items() for line in _metric_lines(sm, SET_TITLES.get(name, name))]
        ),
        "",
        "## Runs",
        "",
        "| Round | Set | run_id | Requirement | Bugs | Surface | Verdict | Cross-validation | detected / broken / tests | Note |",
        "|---|---|---|---|---|---|---|---|---|---|",
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
        lines.append(f"| {r['round']} | {r.get('set') or '-'} | `{r['run_id']}` | {r['requirement_id']} | {bugs} | {r['surface_verdict']} | {r['verdict']} | {cv} | {tally} | {note} |")
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
    parser.add_argument("--dataset", required=True, choices=list(DATASETS), help="phase5 = dev + test (18 combinations)")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--llm", choices=["gemini", "fake"], required=True)
    parser.add_argument("--model", help="gemini model id (required for --llm gemini; fixed for the whole evaluation)")
    parser.add_argument("--pause-s", type=float, default=10.0, help="pause between runs (free-tier pacing)")
    parser.add_argument("--artifacts-dir", type=Path, default=REPO_ROOT / "artifacts")
    parser.add_argument("--results-dir", type=Path, required=True, help="e.g. benchmark/results/phase2r")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH, help="agent policy file (validated before anything runs)")
    args = parser.parse_args(argv)

    try:
        combinations(args.dataset)
        policy = load_policy(args.policy)
        if args.llm == "gemini":
            if not args.model:
                parser.error("--model is required with --llm gemini")
            require_clean_worktree()
            from app import ENV_FILE, load_env_file
            from llm.adapters.gemini import GEMINI_RETRY, GeminiClient

            load_env_file(ENV_FILE)
            GeminiClient(args.model)  # fail fast on a missing key, before any SUT starts
            factory, retry, temperature, model = (lambda: GeminiClient(args.model)), GEMINI_RETRY, 0.0, args.model
            frozen_sha = check_frozen(model, policy) if args.dataset != "dev" else None
        else:
            from testing.scripts import dry_run_llm

            factory, retry, temperature, model = dry_run_llm, NO_RETRY, None, "fake-model"
            frozen_sha = None  # a scripted LLM cannot contaminate anything
    except PolicyError as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        return 2
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
            policy=policy,
            frozen_sha256=frozen_sha,
        )
    except RunnerRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(render_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
