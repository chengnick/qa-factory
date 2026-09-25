"""QA Factory CLI.

    python app.py --requirement REQ-005 --llm fake [--scenario flaky|pass|defect]
    python app.py --requirement REQ-005 --llm gemini --sut-bugs B02 [--model gemini-3.8-flash]
    python app.py --requirement REQ-005 --llm gemini --sut-url http://127.0.0.1:8000

fake:   scripted LLM and tools on a simulated clock; instant and offline.
gemini: real LLM (GEMINI_API_KEY from the environment or .env) and real tools against a SUT.
        Without --sut-url, a fresh SUT is started with SUT_BUGS=--sut-bugs.

Every run writes artifacts/{run_id}/ (spec v3 §4.2): meta.json, trace.json, prompts/ (LLM inputs and
outputs), spans/ (other full-size content), generated/ (tests + owner conftest copy) and reports/ (junit).
Nothing there is ever deleted automatically.

The sealed test-set bugs (benchmark/datasets.py) are refused before Phase 5.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.contracts import RequirementInput
from agents.version import PROMPT_VERSION
from benchmark.datasets import TEST_BUGS, dataset_of
from evaluation.provenance import git_commit, lockfile_sha256
from llm.client import LLMConfigError
from observability.clock import SystemClock
from observability.instrument import Instrumentation, RunContentSink
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import create_tracer_provider, get_tracer
from pipeline import PipelineResult, run_pipeline
from testing import scripts
from testing.fake_clock import FakeClock
from tools.workspace import create_run_workspace, new_run_id

ROOT = Path(__file__).resolve().parent
REQUIREMENTS_DIR = ROOT / "benchmark" / "requirements"
API_REFERENCE = ROOT / "docs" / "sut-api.md"
ENV_FILE = ROOT / ".env"


def parse_bugs(raw: str | None) -> list[str]:
    return sorted({b.strip().upper() for b in (raw or "").split(",") if b.strip()})


def load_env_file(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines; existing environment variables win. Values are never printed."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _run_fake(args: argparse.Namespace, requirement: RequirementInput, sut_bugs: list[str], workspace: Path) -> PipelineResult:
    clock = FakeClock(start_ns=time.time_ns())
    with _instrumentation(workspace, clock) as inst:
        return run_pipeline(
            requirement,
            llm=scripts.fake_llm(args.requirement, clock),
            tools=scripts.fake_tools(args.requirement, args.scenario, clock),
            inst=inst,
            sut_bugs=sut_bugs,
            run_id=workspace.name,
            dataset=dataset_of(sut_bugs),
        )


def _run_gemini(args: argparse.Namespace, requirement: RequirementInput, sut_bugs: list[str], workspace: Path) -> PipelineResult:
    from llm.adapters.gemini import GEMINI_RETRY, GeminiClient
    from sut.launcher import running_sut, wait_healthy
    from tools.factory import real_tools

    load_env_file(ENV_FILE)
    llm = GeminiClient(args.model)
    if args.sut_url:
        wait_healthy(args.sut_url)
        sut = contextlib.nullcontext(args.sut_url.rstrip("/"))
    else:
        sut = running_sut(sut_bugs)
    with sut as url, _instrumentation(workspace, SystemClock()) as inst:
        print(f"SUT: {url}  bugs: {','.join(sut_bugs) or '(none)'}  model: {args.model}", flush=True)
        return run_pipeline(
            requirement,
            llm=llm,
            tools=real_tools(workspace, url),
            inst=inst,
            sut_bugs=sut_bugs,
            llm_retry=GEMINI_RETRY,
            api_reference=API_REFERENCE.read_text(encoding="utf-8"),
            run_id=workspace.name,
            dataset=dataset_of(sut_bugs),
        )


@contextlib.contextmanager
def _instrumentation(workspace: Path, clock):
    """Trace -> {workspace}/trace.json; full-size content -> {workspace}/prompts/ and spans/."""
    provider = create_tracer_provider(JsonFileSpanExporter(workspace, filename="trace.json"))
    try:
        yield Instrumentation(get_tracer(provider), clock, RunContentSink(workspace))
    finally:
        provider.shutdown()


def _write_run_record(workspace: Path, record: dict) -> None:
    (workspace / "meta.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requirement", required=True, help="requirement id, e.g. REQ-005")
    parser.add_argument("--llm", choices=["fake", "gemini"], required=True)
    parser.add_argument("--model", default="gemini-3.8-flash", help="gemini model id (default: gemini-3.8-flash)")
    parser.add_argument("--scenario", choices=scripts.SCENARIOS, default="flaky", help="fake mode only (default: flaky)")
    parser.add_argument("--sut-bugs", default=None, help="bug flags for the SUT / recorded on the run (default: $SUT_BUGS)")
    parser.add_argument("--sut-url", default=None, help="gemini mode: use an already-running SUT instead of starting one")
    parser.add_argument(
        "--artifacts-dir", type=Path, default=ROOT / "artifacts", help="one directory per run: meta.json, trace.json, generated tests (never auto-deleted)"
    )
    parser.add_argument("--allow-test-set", action="store_true", help="Phase 5 only: allow sealed test-set bugs")
    args = parser.parse_args(argv)

    req_file = REQUIREMENTS_DIR / f"{args.requirement}.md"
    if not req_file.is_file():
        parser.error(f"requirement not found: {req_file}")
    requirement = RequirementInput(args.requirement, req_file.read_text(encoding="utf-8"))
    sut_bugs = parse_bugs(args.sut_bugs if args.sut_bugs is not None else os.environ.get("SUT_BUGS"))
    sealed = sorted(set(sut_bugs) & TEST_BUGS)
    if sealed and not args.allow_test_set:
        parser.error(f"{','.join(sealed)} belong to the sealed test set; the pipeline may not run them before Phase 5")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_id = new_run_id()
    workspace = create_run_workspace(args.artifacts_dir, run_id)
    print(f"run: {workspace}", flush=True)
    record: dict = {
        "run_id": run_id,
        "trace_id": None,
        "requirement_id": args.requirement,
        "llm": args.llm,
        "model": args.model if args.llm == "gemini" else "fake-model",
        "temperature": 0.0 if args.llm == "gemini" else None,
        "prompt_version": PROMPT_VERSION,
        "dataset": dataset_of(sut_bugs),
        "scenario": args.scenario if args.llm == "fake" else None,
        "sut_bugs": sut_bugs,
        "sut_url": args.sut_url,
        "git_commit": git_commit(),
        "lockfile_sha256": lockfile_sha256(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    runner = _run_fake if args.llm == "fake" else _run_gemini
    try:
        result = runner(args, requirement, sut_bugs, workspace)
    except LLMConfigError as exc:
        record.update(finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), error=f"LLMConfigError: {exc}")
        _write_run_record(workspace, record)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # unclassified failure: keep the evidence, then crash loudly
        record.update(finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), error=f"{type(exc).__name__}: {exc}")
        _write_run_record(workspace, record)
        raise

    trace_file = workspace / "trace.json"
    record.update(
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        trace_id=result.trace_id,
        trace_file=trace_file.name,
        verdict=result.verdict,
        error=result.error,
        generated_files=sorted(p.relative_to(workspace).as_posix() for p in (workspace / "generated").glob("test_*.py")),
    )
    _write_run_record(workspace, record)

    print(result.report.summary if result.report else f"pipeline failed: {result.error}")
    print(f"verdict: {result.verdict}")
    clock_note = "  (simulated clock)" if args.llm == "fake" else ""
    print(f"trace:   {trace_file}{clock_note}")
    return 0 if result.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
