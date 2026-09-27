"""Permission gate (spec v3 §8.1, v3.1 §8.5): checked inside each tool span, before the tool runs.

The rules come from the policy file (config/agent_policy.yaml); nothing is hard-coded here.
Refused actions never execute; each refusal records a security event (`executed: false`) and raises
PermissionDeniedError (rule R18) or UnknownToolError (rule R6). Every check, allowed or not, adds a
`qa.permission.check` event to the current span and is counted (`stats`).

file_write paths are judged after resolve() + normcase(), in this order:
    1. inside this run's own write area (policy path_prefix)  -> allowed (then scanned for secrets)
    2. policy paths.protected                                 -> PROTECTED_PATH_WRITE (+ GOAL_DRIFT)
    3. policy paths.evidence (any run's directory)            -> EVIDENCE_TAMPER_ATTEMPT
    4. anything else                                          -> PERMISSION_DENIED
A relative path is resolved against both the run workspace and the repo root, so "sut/app.py" is
recognised as an attempt on the real SUT even though file_write would place it under the workspace.

Known limitation: the "artifacts/" in the policy's path_prefix is taken to be the parent directory of the
run workspace (the artifacts root), so test workspaces outside the repo behave like real runs.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from opentelemetry import trace

from observability.redact import find_secret, redact
from permissions.policy import REPO_ROOT, Policy, default_policy
from security.events import SecurityRecorder
from tools.code_policy import check_files
from tools.registry import PermissionDeniedError, UnknownToolError

RUNNERS = ("pytest", "playwright")
UNBOUND_SUT_URL = "http://sut.invalid"  # stands in for {sut_base_url} when no SUT is bound (unit tests)


def __getattr__(name: str) -> Any:
    """Policy-derived views kept under their Phase 3 names (read from the default policy file)."""
    if name == "PERMISSIONS":
        return default_policy().permissions()
    if name == "PROTECTED_DIRS":
        return default_policy().protected
    if name == "EVIDENCE_DIRS":
        return default_policy().evidence
    raise AttributeError(name)


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
        policy: Policy | None = None,
    ) -> None:
        self.recorder = recorder
        self.registered = registered
        self.repo_root = repo_root
        # Without a real workspace (unit tests with fake tools), judge paths against a virtual one.
        self.workspace = workspace or repo_root / "artifacts" / "_unbound_run"
        self.sut_url = sut_url
        self.policy = policy or default_policy()
        self.stats = {"permission_checks": 0, "allowed": 0, "denied": 0}

    # ----------------------------------------------------------------------------------------- entry

    def check(self, agent: str, tool: str, args: Mapping[str, Any]) -> None:
        if tool not in set(self.registered()):
            self._deny("INVALID_TOOL_CALL", agent, tool, tool, "registry", f"tool {tool!r} is not registered", UnknownToolError)
        if self.policy.tool_rule(agent, tool) is None:
            self._deny("PERMISSION_DENIED", agent, tool, tool, f"agents.{agent}.tools",
                       f"agent {agent!r} may not call {tool!r} (policy agents.{agent}.tools)")  # fmt: skip
        if tool == "file_write":
            self._check_write(agent, str(args.get("path", "")), str(args.get("content", "")))
        elif tool == "http_request":
            self._check_route(agent, str(args.get("route", "")))
        elif tool in RUNNERS:
            self._check_code(agent, tool, [str(p) for p in args.get("paths") or []])
        else:
            self._allow(agent, tool, tool, f"agents.{agent}.tools.{tool}")

    # ----------------------------------------------------------------------------------------- paths

    @property
    def artifacts_root(self) -> Path:
        return self.workspace.parent

    def write_area(self, agent: str = "automation") -> Path | None:
        rule = self.policy.tool_rule(agent, "file_write")
        if rule is None:
            return None
        prefix = Policy.expand(rule.path_prefix, run_id=self.workspace.name)
        return self.artifacts_root / prefix.removeprefix("artifacts/")

    def classify_path(self, path: str, agent: str = "automation") -> str:
        """OWN_GENERATED / PROTECTED / EVIDENCE / OUTSIDE."""
        raw = Path(path)
        candidates = [raw] if raw.is_absolute() else [self.workspace / raw, self.repo_root / raw]
        area = self.write_area(agent)
        if area is not None and _inside(candidates[0], area):
            return "OWN_GENERATED"
        if any(_inside(c, self.repo_root / d) for c in candidates for d in self.policy.protected):
            return "PROTECTED"
        evidence_roots = [self.repo_root / d for d in self.policy.evidence]
        if "artifacts" in self.policy.evidence:
            evidence_roots.append(self.artifacts_root)
        if any(_inside(c, root) for c in candidates for root in evidence_roots):
            return "EVIDENCE"
        return "OUTSIDE"

    # ----------------------------------------------------------------------------------------- checks

    def _check_write(self, agent: str, path: str, content: str) -> None:
        where = self.classify_path(path, agent)
        prefix_key = f"agents.{agent}.tools.file_write.path_prefix"
        if where == "OWN_GENERATED":
            if secret := find_secret(content):
                self._deny("SECRET_ACCESS", agent, "file_write", path, "secret_scan", f"credential-shaped string in file content: {secret}")
            self._allow(agent, "file_write", path, prefix_key)
            return
        if where == "PROTECTED":
            self.recorder.record("GOAL_DRIFT", agent=agent, action="file_write", target=path, executed=False,
                                 evidence="attempt to modify the system under test or the reference answers")  # fmt: skip
            self._deny("PROTECTED_PATH_WRITE", agent, "file_write", path, "paths.protected", f"write to protected path {path!r}")
        if where == "EVIDENCE":
            self._deny("EVIDENCE_TAMPER_ATTEMPT", agent, "file_write", path, "paths.evidence", f"write to evidence path {path!r}")
        self._deny("PERMISSION_DENIED", agent, "file_write", path, prefix_key, f"{path!r} is outside this run's write area")

    def _check_route(self, agent: str, route: str) -> None:
        key = f"agents.{agent}.tools.http_request.url_allowlist"
        # Tool contract (Phase 3): a route is a path on the SUT.
        if "://" in route or route.startswith(("//", "\\\\")) or not route.startswith("/"):
            self._deny("PERMISSION_DENIED", agent, "http_request", route, key, f"target {route!r} is not a path on the SUT base URL")
        base = (self.sut_url or UNBOUND_SUT_URL).rstrip("/")
        url = base + route
        allow = [Policy.expand(u, sut_base_url=base) for u in self.policy.tool_rule(agent, "http_request").url_allowlist]
        if not any(url.startswith(prefix.rstrip("/") + "/") or url == prefix for prefix in allow):
            self._deny("PERMISSION_DENIED", agent, "http_request", route, key, f"{url!r} is not in the url_allowlist")
        self._allow(agent, "http_request", route, key)

    def _check_code(self, agent: str, tool: str, paths: list[str]) -> None:
        violations = check_files(self.workspace, paths, sut_url=self.sut_url, policy=self.policy)
        target = ",".join(paths)
        if violations:
            detail = "; ".join(f"{p}:{v.line} {v.kind} {v.detail}" for p, v in violations)
            self._deny("PERMISSION_DENIED", agent, tool, target, "generated_code", f"generated-code policy: {detail}")
        self._allow(agent, tool, target, f"agents.{agent}.tools.{tool}")

    # ----------------------------------------------------------------------------------------- outcome

    def _event(self, agent: str, tool: str, target: str, decision: str, matched: str) -> None:
        self.stats["permission_checks"] += 1
        self.stats["allowed" if decision == "allow" else "denied"] += 1
        span = trace.get_current_span()
        if span.get_span_context().is_valid:
            span.add_event("qa.permission.check",
                           {"agent": agent, "tool": tool, "target": redact(target), "decision": decision, "matched": matched})  # fmt: skip

    def _allow(self, agent: str, tool: str, target: str, matched: str) -> None:
        self._event(agent, tool, target, "allow", matched)

    def _deny(self, type: str, agent: str, action: str, target: str, matched: str, evidence: str,
              exc: type[Exception] = PermissionDeniedError) -> None:  # fmt: skip
        self._event(agent, action, target, "deny", matched)
        self.recorder.record(type, agent=agent, action=action, target=target, executed=False, evidence=evidence)
        raise exc(evidence)
