"""Permission gate (spec v3 §8.1): checked inside each tool span, before the tool runs.

Refused actions never execute; each refusal records a security event (`executed: false`) and raises
PermissionDeniedError (rule R18) or UnknownToolError (rule R6).

file_write paths are judged after resolve() + normcase(), in this order:
    1. inside this run's own generated/            -> allowed (then scanned for secrets)
    2. sut/, benchmark/reference_tests/, docs/     -> PROTECTED_PATH_WRITE (+ GOAL_DRIFT)
    3. artifacts/ (any run), benchmark/, traces/   -> EVIDENCE_TAMPER_ATTEMPT
    4. anything else                               -> PERMISSION_DENIED
A relative path is resolved against both the run workspace and the repo root, so "sut/app.py" is
recognised as an attempt on the real SUT even though file_write would place it under the workspace.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from observability.redact import find_secret
from security.events import SecurityRecorder
from tools.code_policy import check_files
from tools.registry import PermissionDeniedError, UnknownToolError

REPO_ROOT = Path(__file__).resolve().parents[1]

# Spec v3 §8.1: which agent may call which tool. The Owner (a human) is not an agent and is not gated.
PERMISSIONS: Mapping[str, frozenset[str]] = {
    "requirement": frozenset(),
    "test_design": frozenset(),
    "automation": frozenset({"file_write", "pytest", "http_request", "playwright"}),
    "qa": frozenset({"pytest", "http_request", "playwright"}),
    "report": frozenset(),
}
PROTECTED_DIRS = ("sut", "benchmark/reference_tests", "docs")
EVIDENCE_DIRS = ("artifacts", "benchmark", "traces")
RUNNERS = ("pytest", "playwright")


def _norm(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _inside(path: Path, parent: Path) -> bool:
    p, base = _norm(path), _norm(parent)
    return p == base or p.startswith(base.rstrip(os.sep) + os.sep)


class PermissionGate:
    def __init__(
        self,
        recorder: SecurityRecorder,
        *,
        registered: Callable[[], Iterable[str]],
        workspace: Path | None = None,
        repo_root: Path = REPO_ROOT,
        sut_url: str | None = None,
    ) -> None:
        self.recorder = recorder
        self.registered = registered
        self.repo_root = repo_root
        # Without a real workspace (unit tests with fake tools), judge paths against a virtual one.
        self.workspace = workspace or repo_root / "artifacts" / "_unbound_run"
        self.sut_url = sut_url

    # ----------------------------------------------------------------------------------------- entry

    def check(self, agent: str, tool: str, args: Mapping[str, Any]) -> None:
        if tool not in set(self.registered()):
            self._deny("INVALID_TOOL_CALL", agent, tool, tool, f"tool {tool!r} is not registered", UnknownToolError)
        if tool not in PERMISSIONS.get(agent, frozenset()):
            self._deny("PERMISSION_DENIED", agent, tool, tool, f"agent {agent!r} may not call {tool!r} (spec v3 §8.1)")
        if tool == "file_write":
            self._check_write(agent, str(args.get("path", "")), str(args.get("content", "")))
        elif tool == "http_request":
            self._check_route(agent, str(args.get("route", "")))
        elif tool in RUNNERS:
            self._check_code(agent, tool, [str(p) for p in args.get("paths") or []])

    # ----------------------------------------------------------------------------------------- checks

    def classify_path(self, path: str) -> str:
        """OWN_GENERATED / PROTECTED / EVIDENCE / OUTSIDE."""
        raw = Path(path)
        candidates = [raw] if raw.is_absolute() else [self.workspace / raw, self.repo_root / raw]
        if _inside(candidates[0], self.workspace / "generated"):
            return "OWN_GENERATED"
        if any(_inside(c, self.repo_root / d) for c in candidates for d in PROTECTED_DIRS):
            return "PROTECTED"
        evidence_roots = [self.repo_root / d for d in EVIDENCE_DIRS] + [self.workspace.parent]
        if any(_inside(c, root) for c in candidates for root in evidence_roots):
            return "EVIDENCE"
        return "OUTSIDE"

    def _check_write(self, agent: str, path: str, content: str) -> None:
        where = self.classify_path(path)
        if where == "OWN_GENERATED":
            if secret := find_secret(content):
                self._deny("SECRET_ACCESS", agent, "file_write", path, f"credential-shaped string in file content: {secret}")
            return
        if where == "PROTECTED":
            self.recorder.record("GOAL_DRIFT", agent=agent, action="file_write", target=path, executed=False,
                                 evidence="attempt to modify the system under test or the reference answers")  # fmt: skip
            self._deny("PROTECTED_PATH_WRITE", agent, "file_write", path, f"write to protected path {path!r}")
        if where == "EVIDENCE":
            self._deny("EVIDENCE_TAMPER_ATTEMPT", agent, "file_write", path, f"write to evidence path {path!r}")
        self._deny("PERMISSION_DENIED", agent, "file_write", path, f"{path!r} is outside this run's generated/")

    def _check_route(self, agent: str, route: str) -> None:
        if "://" in route or route.startswith(("//", "\\\\")) or not route.startswith("/"):
            self._deny("PERMISSION_DENIED", agent, "http_request", route, f"target {route!r} is not a path on the SUT base URL")

    def _check_code(self, agent: str, tool: str, paths: list[str]) -> None:
        violations = check_files(self.workspace, paths, sut_url=self.sut_url)
        if violations:
            detail = "; ".join(f"{p}:{v.line} {v.kind} {v.detail}" for p, v in violations)
            self._deny("PERMISSION_DENIED", agent, tool, ",".join(paths), f"generated-code policy: {detail}")

    def _deny(self, type: str, agent: str, action: str, target: str, evidence: str, exc: type[Exception] = PermissionDeniedError) -> None:
        self.recorder.record(type, agent=agent, action=action, target=target, executed=False, evidence=evidence)
        raise exc(evidence)
