"""Cross-validation (spec v3 §6): run the final generated tests on a fresh bug SUT and a fresh clean SUT.

Both builds are symmetric: a brand-new SUT process each (in-memory DB, identical seed: users 1-4, no
projects), the same test files in the same order (API file(s) via `pytest`, then UI file(s) via
`playwright`), the same tools, retry policies and whitelisted environment. The pipeline's own QA run is
not reused; it only feeds the surface verdict.

Each build starts with a SUT health check. If either build's SUT is not healthy, cross-validation is
INCOMPLETE (layer ENV, symptom CONNECTION, rule R1): no test is judged and none counts toward test health.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ContextManager

from agents.contracts import AutomationResult
from opentelemetry.trace import Status, StatusCode

from observability.instrument import Instrumentation, TracedToolRegistry, start_span
from observability.redact import redact
from sut.launcher import SUTStartupError, running_sut
from tools.factory import real_tools
from tools.registry import ToolError

SutFactory = Callable[[Sequence[str]], ContextManager[str]]

_HTTP_5XX = re.compile(r"\b5\d\d\b")


# --------------------------------------------------------------------------- per-test decision (§6.2)


@dataclass(frozen=True)
class TestDecision:
    __test__ = False

    node_id: str
    bug_outcome: str  # PASS / FAIL / ERROR / SKIP / MISSING
    clean_outcome: str
    decision: str  # DETECTED / NOT_DETECTED / BROKEN / PASS
    rule: str | None  # R10 / R11 / R12 / R13 / MISSING
    symptom: str | None
    evidence: str


def decide(node_id: str, bug: dict | None, clean: dict | None, *, bugs_enabled: bool) -> TestDecision:
    """Spec v3 §6.2, plus: a clean-build ERROR counts as FAIL; a test present in one build only is BROKEN;
    SKIP is not a detection. With no bug enabled (clean dataset) both builds are clean, so any disagreement
    is nondeterminism and counts as BROKEN (R13), and DETECTED is impossible."""
    b = bug["outcome"] if bug else "MISSING"
    c = clean["outcome"] if clean else "MISSING"
    b_msg = bug["message"] if bug else ""
    c_msg = clean["message"] if clean else ""

    def result(decision: str, rule: str | None, symptom: str | None, evidence: str) -> TestDecision:
        return TestDecision(node_id, b, c, decision, rule, symptom, evidence)

    if bug is None or clean is None:
        missing = "bug" if bug is None else "clean"
        return result("BROKEN", "MISSING", "CRASH", f"MISSING_IN_{missing}_build")
    if b == "ERROR":
        return result("BROKEN", "R10", "CRASH", f"bug build: {b_msg}")
    if "SKIP" in (b, c):
        return result("NOT_DETECTED", None, None, f"skipped (bug={b}, clean={c})")
    clean_failed = c in ("FAIL", "ERROR")
    if not bugs_enabled:
        if b == "PASS" and not clean_failed:
            return result("PASS", None, None, "")
        if b == "FAIL" and clean_failed:
            return result("BROKEN", "R12", "ASSERTION", f"fails on a clean SUT: {b_msg}")
        return result("BROKEN", "R13", "ASSERTION", f"nondeterministic on identical clean SUTs: bug={b} ({b_msg}) clean={c} ({c_msg})")
    if b == "FAIL" and not clean_failed:
        symptom = "HTTP_5XX" if _HTTP_5XX.search(b_msg) and "==" in b_msg else "ASSERTION"
        return result("DETECTED", "R11", symptom, f"bug build: {b_msg}")
    if b == "FAIL" and clean_failed:
        return result("BROKEN", "R12", "ASSERTION", f"bug build: {b_msg} | clean build: {c_msg}")
    if b == "PASS" and clean_failed:
        return result("BROKEN", "R13", "ASSERTION", f"clean build: {c_msg}")
    return result("NOT_DETECTED", None, None, "passes on both builds")


def compare(bug_results: list[dict], clean_results: list[dict], *, bugs_enabled: bool) -> list[TestDecision]:
    bug_by_id = {r["node_id"]: r for r in bug_results}
    clean_by_id = {r["node_id"]: r for r in clean_results}
    order = list(dict.fromkeys([*bug_by_id, *clean_by_id]))
    return [decide(node, bug_by_id.get(node), clean_by_id.get(node), bugs_enabled=bugs_enabled) for node in order]


def run_verdict(decisions: list[TestDecision], *, bugs_enabled: bool) -> str:
    """Spec v3 §6.3 (bugs enabled). For the clean dataset: any broken test -> TEST_BROKEN, else PASS."""
    if not decisions:
        return "TEST_BROKEN"
    broken = any(d.decision == "BROKEN" for d in decisions)
    if bugs_enabled:
        if any(d.decision == "DETECTED" for d in decisions):
            return "DEFECT_FOUND"
        return "TEST_BROKEN" if broken else "MISSED"
    return "TEST_BROKEN" if broken else "PASS"


# --------------------------------------------------------------------------- builds


@dataclass
class BuildResult:
    build: str  # "bug" | "clean"
    sut_bugs: list[str]
    status: str = "OK"  # OK / ENV_BLOCKED / INCOMPLETE
    reason: str | None = None
    results: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)  # one per tool call: tool, paths, exit_code, attempts, junit
    log_file: str | None = None


def files_by_surface(automation: AutomationResult) -> tuple[list[str], list[str]]:
    return [f.path for f in automation.files if f.surface == "api"], [f.path for f in automation.files if f.surface == "ui"]


def _hashes(workspace: Path, paths: Sequence[str]) -> dict[str, str]:
    return {p: hashlib.sha256((workspace / p).read_bytes()).hexdigest() for p in paths}


def run_build(
    build: str,
    sut_bugs: Sequence[str],
    workspace: Path,
    api_files: Sequence[str],
    ui_files: Sequence[str],
    inst: Instrumentation,
    sut_factory: SutFactory,
) -> BuildResult:
    result = BuildResult(build, list(sut_bugs))
    log_lines: list[str] = []
    attrs = {"qa.eval.build": build, "qa.run.sut_bugs": list(sut_bugs)}
    with start_span(inst, "evaluation.build", attrs) as span, contextlib.ExitStack() as stack:
        try:
            url = stack.enter_context(sut_factory(sut_bugs))
        except SUTStartupError as exc:
            return _env_blocked(result, span, f"SUT did not start: {exc}")
        tools = TracedToolRegistry(real_tools(workspace, url), inst)
        # R1: health check before running anything.
        try:
            status = tools.call("http_request", method="GET", route="/health").data.get("status_code")
        except ToolError as exc:
            return _env_blocked(result, span, f"health check failed: {type(exc).__name__}: {exc}")
        if status != 200:
            return _env_blocked(result, span, f"health check returned {status}")
        for tool, paths in (("pytest", api_files), ("playwright", ui_files)):
            if not paths:
                continue
            try:
                run = tools.call(tool, paths=list(paths))
            except ToolError as exc:
                result.status, result.reason = "INCOMPLETE", f"{tool}: {type(exc).__name__}: {exc}"
                span.set_status(Status(StatusCode.ERROR, result.reason))
                log_lines.append(f"===== {tool} {' '.join(paths)} -> {result.reason}")
                break
            result.results.extend(run.data.get("results", []))
            result.runs.append(
                {"tool": tool, "paths": list(paths), "exit_code": run.exit_code, "attempts": run.attempts, "junit": run.data.get("junit")}
            )
            log_lines += [f"===== {tool} {' '.join(paths)} (exit {run.exit_code}, attempts {run.attempts})", run.stdout]
    log = workspace / "pytest" / f"{build}_build.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text(redact("\n".join(log_lines)) + "\n", encoding="utf-8")
    result.log_file = log.relative_to(workspace).as_posix()
    return result


def _env_blocked(result: BuildResult, span: Any, reason: str) -> BuildResult:
    result.status, result.reason = "ENV_BLOCKED", reason
    span.set_status(Status(StatusCode.ERROR, reason))
    span.set_attribute("qa.failure.layer", "ENV")
    span.set_attribute("qa.failure.symptom", "CONNECTION")
    span.set_attribute("qa.failure.rule", "R1")
    return result


# --------------------------------------------------------------------------- run level


@dataclass
class DifferentialResult:
    status: str  # COMPLETE / ENV_BLOCKED / INCOMPLETE / TAMPERED
    verdict: str
    bugs_enabled: bool
    sut_bugs: list[str]
    decisions: list[TestDecision] = field(default_factory=list)
    builds: list[BuildResult] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    reason: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        c = {k: sum(d.decision == k for d in self.decisions) for k in ("DETECTED", "NOT_DETECTED", "BROKEN", "PASS")}
        return {"detected": c["DETECTED"], "missed": c["NOT_DETECTED"], "broken": c["BROKEN"], "passed": c["PASS"], "tests": len(self.decisions)}

    @property
    def test_health(self) -> dict[str, int] | None:
        """Healthy = not R10/R12/R13/MISSING. None when cross-validation did not complete (not counted)."""
        if self.status != "COMPLETE":
            return None
        return {"healthy": sum(d.decision != "BROKEN" for d in self.decisions), "total": len(self.decisions)}

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "verdict": self.verdict,
            "reason": self.reason,
            "bugs_enabled": self.bugs_enabled,
            "sut_bugs": self.sut_bugs,
            "counts": self.counts,
            "test_health": self.test_health,
            "file_hashes": self.file_hashes,
            "builds": [asdict(b) for b in self.builds],
            "decisions": [asdict(d) for d in self.decisions],
        }


def run_differential(
    workspace: Path,
    automation: AutomationResult,
    sut_bugs: Sequence[str],
    inst: Instrumentation,
    sut_factory: SutFactory = running_sut,
) -> DifferentialResult:
    api_files, ui_files = files_by_surface(automation)
    bugs_enabled = bool(sut_bugs)
    before = _hashes(workspace, [*api_files, *ui_files])
    attrs = {"qa.eval.sut_bugs": list(sut_bugs), "qa.eval.files": [*api_files, *ui_files]}
    with start_span(inst, "evaluation.differential", attrs) as span:
        bug = run_build("bug", sut_bugs, workspace, api_files, ui_files, inst, sut_factory)
        clean = run_build("clean", [], workspace, api_files, ui_files, inst, sut_factory)
        after = _hashes(workspace, [*api_files, *ui_files])
        result = DifferentialResult("COMPLETE", "", bugs_enabled, list(sut_bugs), builds=[bug, clean], file_hashes=before)
        blocked = [b for b in (bug, clean) if b.status == "ENV_BLOCKED"]
        incomplete = [b for b in (bug, clean) if b.status == "INCOMPLETE"]
        if blocked:
            result.status, result.verdict = "ENV_BLOCKED", "ENV_BLOCKED"
            result.reason = "; ".join(f"{b.build} build: {b.reason}" for b in blocked)
            span.set_attribute("qa.failure.layer", "ENV")
            span.set_attribute("qa.failure.symptom", "CONNECTION")
            span.set_attribute("qa.failure.rule", "R1")
        elif before != after:
            result.status, result.verdict, result.reason = "TAMPERED", "TEST_BROKEN", "generated test files changed during cross-validation"
            span.set_attribute("qa.failure.layer", "HARNESS")
        elif incomplete:
            result.status, result.verdict = "INCOMPLETE", "TEST_BROKEN"
            result.reason = "; ".join(f"{b.build} build: {b.reason}" for b in incomplete)
            span.set_attribute("qa.failure.layer", "HARNESS")
        else:
            result.decisions = compare(bug.results, clean.results, bugs_enabled=bugs_enabled)
            result.verdict = run_verdict(result.decisions, bugs_enabled=bugs_enabled)
            for d in result.decisions:
                span.add_event(
                    "qa.test",
                    {
                        "qa.test.id": d.node_id,
                        "qa.test.bug_outcome": d.bug_outcome,
                        "qa.test.clean_outcome": d.clean_outcome,
                        "qa.test.decision": d.decision,
                        "qa.test.rule": d.rule or "",
                    },
                    timestamp=inst.clock.now_ns(),
                )
        span.set_attribute("qa.eval.status", result.status)
        span.set_attribute("qa.eval.verdict", result.verdict)
        for key, value in result.counts.items():
            span.set_attribute(f"qa.eval.{key}", value)
        if result.status != "COMPLETE":
            span.set_status(Status(StatusCode.ERROR, result.reason or result.status))
    (workspace / "differential.json").write_text(json.dumps(result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result

