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
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.contracts import RequirementInput
from benchmark.datasets import TEST_BUGS
from evaluation.run import base_meta, execute_run, instrumentation, write_meta
from llm.client import LLMConfigError
from pipeline import run_pipeline
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


def _run_fake(args: argparse.Namespace, sut_bugs: list[str]) -> tuple[Path, dict]:
    """Scripted LLM and scripted tools on a simulated clock (no SUT, no network)."""
    run_id = new_run_id()
    workspace = create_run_workspace(args.artifacts_dir, run_id)
    meta = base_meta(run_id, args.requirement, llm="fake", model="fake-model", temperature=None, sut_bugs=sut_bugs)
    meta["scenario"] = args.scenario
    requirement = RequirementInput(args.requirement, (REQUIREMENTS_DIR / f"{args.requirement}.md").read_text(encoding="utf-8"))
    clock = FakeClock(start_ns=time.time_ns())
    try:
        with instrumentation(workspace, clock) as inst:
            result = run_pipeline(
                requirement,
                llm=scripts.fake_llm(args.requirement, clock),
                tools=scripts.fake_tools(args.requirement, args.scenario, clock),
                inst=inst,
                sut_bugs=sut_bugs,
                run_id=run_id,
                dataset=meta["dataset"],
            )
    except Exception as exc:  # unclassified failure: keep the evidence, then crash loudly
        meta.update(error=f"{type(exc).__name__}: {exc}", finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        write_meta(workspace, meta)
        raise
    meta.update(
        trace_id=result.trace_id,
        trace_file="trace.json",
        verdict=result.verdict,
        surface_verdict=result.surface_verdict,
        error=result.error,
        generated_files=[],
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    write_meta(workspace, meta)
    return workspace, meta


def _run_gemini(args: argparse.Namespace, sut_bugs: list[str]) -> tuple[Path, dict]:
    """Real LLM and real tools; not in evaluation mode (no cross-validation: results are unverified)."""
    from llm.adapters.gemini import GEMINI_RETRY, GeminiClient
    from sut.launcher import wait_healthy

    load_env_file(ENV_FILE)
    llm = GeminiClient(args.model)
    if args.sut_url:
        wait_healthy(args.sut_url)
    return execute_run(
        requirement_id=args.requirement,
        sut_bugs=sut_bugs,
        llm=llm,
        llm_kind="gemini",
        model=args.model,
        artifacts_dir=args.artifacts_dir,
        temperature=0.0,
        llm_retry=GEMINI_RETRY,
        differential=False,
        sut_url=args.sut_url.rstrip("/") if args.sut_url else None,
    )


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

    if not (REQUIREMENTS_DIR / f"{args.requirement}.md").is_file():
        parser.error(f"requirement not found: {args.requirement}")
    sut_bugs = parse_bugs(args.sut_bugs if args.sut_bugs is not None else os.environ.get("SUT_BUGS"))
    sealed = sorted(set(sut_bugs) & TEST_BUGS)
    if sealed and not args.allow_test_set:
        parser.error(f"{','.join(sealed)} belong to the sealed test set; the pipeline may not run them before Phase 5")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        workspace, meta = _run_fake(args, sut_bugs) if args.llm == "fake" else _run_gemini(args, sut_bugs)
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"run:     {workspace}")
    if meta.get("error"):
        print(f"pipeline failed: {meta['error']}")
    print(f"verdict: {meta.get('verdict')} (unverified: no cross-validation outside evaluation mode)")
    clock_note = "  (simulated clock)" if args.llm == "fake" else ""
    print(f"trace:   {workspace / 'trace.json'}{clock_note}")
    return 0 if not meta.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
