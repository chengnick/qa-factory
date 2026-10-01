"""Static policy for generated test code (AST). A check, not a sandbox.

The lists come from the policy file (config/agent_policy.yaml, generated_code). With the default policy,
before a generated test file runs, its AST must only:
    - import pytest, httpx, uuid, re, playwright (the imports the automation prompt allows)
    - avoid the builtins open, exec, eval, compile, __import__, getattr and the name __builtins__
    - avoid the attributes __dict__, __class__, __subclasses__, __builtins__
    - avoid hard-coded URLs other than the SUT base URL (network targets besides the SUT)

It catches careless or prompt-injected code. Determined code can evade a static check (string tricks,
encodings, dynamic attribute access through allowed modules); real containment is L1 isolation (Phase 4).
A file that does not parse is not a policy violation: pytest reports it as a collection error (R9).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from permissions.policy import Policy, default_policy

_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s'\"]+")


def __getattr__(name: str) -> Any:
    """Phase 3 names, now read from the default policy file."""
    rules = default_policy().generated_code
    if name == "ALLOWED_IMPORTS":
        return frozenset(rules.allowed_imports)
    if name == "FORBIDDEN_NAMES":
        return frozenset(rules.banned_names)
    if name == "FORBIDDEN_ATTRIBUTES":
        return frozenset(rules.banned_attributes)
    raise AttributeError(name)


@dataclass(frozen=True)
class Violation:
    kind: str  # FORBIDDEN_IMPORT / FORBIDDEN_NAME / FORBIDDEN_ATTRIBUTE / HARDCODED_URL
    detail: str
    line: int


def check_source(source: str, *, sut_url: str | None = None, policy: Policy | None = None) -> list[Violation]:
    rules = (policy or default_policy()).generated_code
    allowed_imports, banned_names, banned_attributes = set(rules.allowed_imports), set(rules.banned_names), set(rules.banned_attributes)
    # {sut_base_url} expands to the bound SUT; without one it stays unexpanded and matches no URL.
    url_allowlist = [Policy.expand(u, sut_base_url=sut_url.rstrip("/")) if sut_url else u for u in rules.url_allowlist]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    violations: list[Violation] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed_imports:
                    violations.append(Violation("FORBIDDEN_IMPORT", f"import {alias.name}", line))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.split(".")[0] not in allowed_imports:
                violations.append(Violation("FORBIDDEN_IMPORT", f"from {'.' * node.level}{module} import ...", line))
        elif isinstance(node, ast.Name) and node.id in banned_names:
            violations.append(Violation("FORBIDDEN_NAME", node.id, line))
        elif isinstance(node, ast.Attribute) and node.attr in banned_attributes:
            violations.append(Violation("FORBIDDEN_ATTRIBUTE", f".{node.attr}", line))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for url in _URL.findall(node.value):
                if not any(_within(url, prefix) for prefix in url_allowlist if "{" not in prefix):
                    violations.append(Violation("HARDCODED_URL", url, line))
    return violations


def _within(url: str, prefix: str) -> bool:
    """The URL is the allowlisted one or lies under it: the prefix must end where a path, query or fragment begins.
    A plain startswith let "http://127.0.0.1:8765@evil.test", ":87650" and ":8765.evil.test" pass as the SUT."""
    base = prefix.rstrip("/")
    return url == base or (url.startswith(base) and url[len(base)] in "/?#")


def check_files(workspace: Path, paths: Iterable[str], *, sut_url: str | None = None, policy: Policy | None = None) -> list[tuple[str, Violation]]:
    found = []
    for rel in paths:
        path = workspace / rel
        if path.is_file():
            source = path.read_text(encoding="utf-8", errors="replace")
            found += [(rel, v) for v in check_source(source, sut_url=sut_url, policy=policy)]
    return found
