"""QA Factory CLI.

    python app.py --requirement REQ-005 --llm fake [--scenario flaky|pass|defect]
    python app.py --requirement REQ-005 --llm gemini --sut-bugs B02 [--model gemini-3.8-flash]
    python app.py --requirement REQ-005 --llm gemini --sut-url http://127.0.0.1:8000

fake:   scripted LLM and tools on a simulated clock; instant and offline.
gemini: real LLM (GEMINI_API_KEY from the environment or .env) and real tools against a SUT.
        Without --sut-url, a fresh SUT is started with SUT_BUGS=--sut-bugs.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from pathlib import Path

from agents.contracts import RequirementInput
from llm.client import LLMConfigError
from observability.clock import SystemClock
from observability.instrument import FileContentSink, Instrumentation
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import create_tracer_provider, get_tracer
from pipeline import PipelineResult, run_pipeline
from testing import scripts
from testing.fake_clock import FakeClock

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


def _run_fake(args: argparse.Namespace, requirement: RequirementInput, sut_bugs: list[str]) -> PipelineResult:
    clock = FakeClock(start_ns=time.time_ns())
    with _instrumentation(args.traces_dir, clock) as inst:
        return run_pipeline(
            requirement,
            llm=scripts.fake_llm(args.requirement, clock),
            tools=scripts.fake_tools(args.requirement, args.scenario, clock),
            inst=inst,
            sut_bugs=sut_bugs,
        )


def _run_gemini(args: argparse.Namespace, requirement: RequirementInput, sut_bugs: list[str]) -> PipelineResult:
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
    with sut as url, _instrumentation(args.traces_dir, SystemClock()) as inst:
        print(f"SUT: {url}  bugs: {','.join(sut_bugs) or '(none)'}  model: {args.model}", flush=True)
        return run_pipeline(
            requirement,
            llm=llm,
            tools=real_tools(ROOT, url),
            inst=inst,
            sut_bugs=sut_bugs,
            llm_retry=GEMINI_RETRY,
            api_reference=API_REFERENCE.read_text(encoding="utf-8"),
        )


@contextlib.contextmanager
def _instrumentation(traces_dir: Path, clock):
    provider = create_tracer_provider(JsonFileSpanExporter(traces_dir))
    try:
        yield Instrumentation(get_tracer(provider), clock, FileContentSink(traces_dir))
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requirement", required=True, help="requirement id, e.g. REQ-005")
    parser.add_argument("--llm", choices=["fake", "gemini"], required=True)
    parser.add_argument("--model", default="gemini-3.8-flash", help="gemini model id (default: gemini-3.8-flash)")
    parser.add_argument("--scenario", choices=scripts.SCENARIOS, default="flaky", help="fake mode only (default: flaky)")
    parser.add_argument("--sut-bugs", default=None, help="bug flags for the SUT / recorded on the run (default: $SUT_BUGS)")
    parser.add_argument("--sut-url", default=None, help="gemini mode: use an already-running SUT instead of starting one")
    parser.add_argument("--traces-dir", type=Path, default=ROOT / "traces")
    args = parser.parse_args(argv)

    req_file = REQUIREMENTS_DIR / f"{args.requirement}.md"
    if not req_file.is_file():
        parser.error(f"requirement not found: {req_file}")
    requirement = RequirementInput(args.requirement, req_file.read_text(encoding="utf-8"))
    sut_bugs = parse_bugs(args.sut_bugs if args.sut_bugs is not None else os.environ.get("SUT_BUGS"))

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = _run_fake(args, requirement, sut_bugs) if args.llm == "fake" else _run_gemini(args, requirement, sut_bugs)
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(result.report.summary if result.report else f"pipeline failed: {result.error}")
    print(f"verdict: {result.verdict}")
    clock_note = "  (simulated clock)" if args.llm == "fake" else ""
    print(f"trace:   {args.traces_dir / (result.trace_id + '.json')}{clock_note}")
    return 0 if result.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
