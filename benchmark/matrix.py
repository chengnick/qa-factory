"""Phase 0 acceptance matrix.

Runs benchmark/reference_tests under: all bugs off, each bug alone, all bugs on.
Expected: a reference test FAILs (assertion failure, not an error) iff its bug is enabled.

    python -m benchmark.matrix [--jobs N] [--out PATH]

Prints a Markdown table, writes it to benchmark/results/phase0_matrix.md, exits 1 on any mismatch.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REF_TESTS = ROOT / "benchmark" / "reference_tests"
DEFAULT_OUT = ROOT / "benchmark" / "results" / "phase0_matrix.md"
TEST_BUG = re.compile(r"test_(b\d{2})_", re.IGNORECASE)


@dataclass
class ConfigResult:
    name: str
    enabled: tuple[str, ...]
    outcomes: dict[str, str]  # bug id of the reference test -> PASS / FAIL / ERROR / SKIP / MISSING
    duration_s: float
    output_tail: str

    def expected(self, bug_id: str) -> str:
        return "FAIL" if bug_id in self.enabled else "PASS"

    def mismatches(self, bug_ids: list[str]) -> list[str]:
        return [b for b in bug_ids if self.outcomes.get(b, "MISSING") != self.expected(b)]


def load_bug_ids() -> list[str]:
    return [b["id"] for b in yaml.safe_load((ROOT / "benchmark" / "bugs.yaml").read_text(encoding="utf-8"))]


def configs(bug_ids: list[str]) -> list[tuple[str, tuple[str, ...]]]:
    return [("clean", ()), *((b, (b,)) for b in bug_ids), ("all", tuple(bug_ids))]


def parse_junit(path: Path) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        m = TEST_BUG.search(f"{case.get('classname', '')}.{case.get('name', '')}")
        if not m:
            continue
        if case.find("failure") is not None:
            outcome = "FAIL"
        elif case.find("error") is not None:
            outcome = "ERROR"
        elif case.find("skipped") is not None:
            outcome = "SKIP"
        else:
            outcome = "PASS"
        bug_id = m.group(1).upper()
        # One test per bug by contract; if there are several, the worst outcome wins.
        rank = ["PASS", "SKIP", "FAIL", "ERROR"]
        prev = outcomes.get(bug_id, "PASS")
        outcomes[bug_id] = max(prev, outcome, key=rank.index)
    return outcomes


def run_config(name: str, enabled: tuple[str, ...], workdir: Path) -> ConfigResult:
    junit = workdir / f"{name}.xml"
    env = {**os.environ, "SUT_BUGS": ",".join(enabled), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    env.pop("SUT_BASE_URL", None)  # each config needs its own SUT process
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(REF_TESTS), "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    outcomes = parse_junit(junit) if junit.exists() else {}
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
    return ConfigResult(name, enabled, outcomes, time.monotonic() - started, tail)


def render(results: list[ConfigResult], bug_ids: list[str]) -> str:
    total_cells = len(results) * len(bug_ids)
    bad = sum(len(r.mismatches(bug_ids)) for r in results)
    lines = [
        "# Phase 0 reference-test matrix",
        "",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Python {sys.version.split()[0]} · {sys.platform}",
        "- Expected: a reference test **FAIL**s iff its bug is enabled, otherwise **PASS**es.",
        "- Cell: actual outcome; ✅ matches expectation, ❌ does not. Bold = the bug is enabled in that row.",
        "",
        "| SUT_BUGS | " + " | ".join(bug_ids) + " | Result | Time |",
        "|---|" + "---|" * len(bug_ids) + "---|---|",
    ]
    for r in results:
        cells = []
        for b in bug_ids:
            actual = r.outcomes.get(b, "MISSING")
            mark = "✅" if actual == r.expected(b) else "❌"
            text = f"{mark} {actual}"
            cells.append(f"**{text}**" if b in r.enabled else text)
        label = "(none)" if not r.enabled else ("all" if r.name == "all" else ",".join(r.enabled))
        verdict = "OK" if not r.mismatches(bug_ids) else f"{len(r.mismatches(bug_ids))} mismatch"
        lines.append(f"| `{label}` | " + " | ".join(cells) + f" | {verdict} | {r.duration_s:.1f}s |")
    lines += ["", f"**{total_cells - bad}/{total_cells} cells match** → {'PASS' if bad == 0 else 'FAIL'}"]
    for r in results:
        if r.mismatches(bug_ids):
            lines += ["", f"<details><summary>pytest output: {r.name}</summary>", "", "```", r.output_tail, "```", "</details>"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jobs", type=int, default=4, help="configurations to run in parallel (default 4)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    bug_ids = load_bug_ids()
    plan = configs(bug_ids)
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda c: run_config(c[0], c[1], Path(tmp)), plan))

    report = render(results, bug_ids)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(report)
    print(f"written to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return 0 if all(not r.mismatches(bug_ids) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
