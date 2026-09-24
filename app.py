"""QA Factory CLI.

    python app.py --requirement REQ-005 --llm fake [--scenario flaky|pass|defect] [--sut-bugs B02]

Phase 1: only `--llm fake` exists. The LLM and the tools are scripted fakes and time runs on a
simulated clock that starts at the current time, so the run is instant and fully offline.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from agents.contracts import RequirementInput
from observability.instrument import FileContentSink, Instrumentation
from observability.json_exporter import JsonFileSpanExporter
from observability.setup import create_tracer_provider, get_tracer
from pipeline import run_pipeline
from testing import scripts
from testing.fake_clock import FakeClock

ROOT = Path(__file__).resolve().parent
REQUIREMENTS_DIR = ROOT / "benchmark" / "requirements"


def parse_bugs(raw: str | None) -> list[str]:
    return sorted({b.strip().upper() for b in (raw or "").split(",") if b.strip()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--requirement", required=True, help="requirement id, e.g. REQ-005")
    parser.add_argument("--llm", choices=["fake"], required=True, help="LLM backend (Phase 1: fake only)")
    parser.add_argument("--scenario", choices=scripts.SCENARIOS, default="flaky", help="fake tool behaviour (default: flaky)")
    parser.add_argument("--sut-bugs", default=None, help="bug flags recorded on the run (default: $SUT_BUGS)")
    parser.add_argument("--traces-dir", type=Path, default=ROOT / "traces")
    args = parser.parse_args(argv)

    req_file = REQUIREMENTS_DIR / f"{args.requirement}.md"
    if not req_file.is_file():
        parser.error(f"requirement not found: {req_file}")
    requirement = RequirementInput(args.requirement, req_file.read_text(encoding="utf-8"))
    sut_bugs = parse_bugs(args.sut_bugs if args.sut_bugs is not None else os.environ.get("SUT_BUGS"))

    clock = FakeClock(start_ns=time.time_ns())
    exporter = JsonFileSpanExporter(args.traces_dir)
    provider = create_tracer_provider(exporter)
    inst = Instrumentation(get_tracer(provider), clock, FileContentSink(args.traces_dir))
    try:
        result = run_pipeline(
            requirement,
            llm=scripts.fake_llm(args.requirement, clock),
            tools=scripts.fake_tools(args.requirement, args.scenario, clock),
            inst=inst,
            sut_bugs=sut_bugs,
        )
    finally:
        provider.shutdown()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(result.report.summary if result.report else f"pipeline failed: {result.error}")
    print(f"verdict: {result.verdict}")
    print(f"trace:   {args.traces_dir / (result.trace_id + '.json')}  (simulated clock)")
    return 0 if result.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
