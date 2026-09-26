"""Static policy for generated test code (AST). A check, not a sandbox.

Before a generated test file runs, its AST must only:
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

ALLOWED_IMPORTS = frozenset({"pytest", "httpx", "uuid", "re", "playwright", "__future__"})
FORBIDDEN_NAMES = frozenset({"open", "exec", "eval", "compile", "__import__", "getattr", "__builtins__"})
FORBIDDEN_ATTRIBUTES = frozenset({"__dict__", "__class__", "__subclasses__", "__builtins__"})
_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s'\"]+")


@dataclass(frozen=True)
class Violation:
    kind: str  # FORBIDDEN_IMPORT / FORBIDDEN_NAME / FORBIDDEN_ATTRIBUTE / HARDCODED_URL
    detail: str
    line: int


def check_source(source: str, *, sut_url: str | None = None) -> list[Violation]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    violations: list[Violation] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    violations.append(Violation("FORBIDDEN_IMPORT", f"import {alias.name}", line))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level or module.split(".")[0] not in ALLOWED_IMPORTS:
                violations.append(Violation("FORBIDDEN_IMPORT", f"from {'.' * node.level}{module} import ...", line))
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.append(Violation("FORBIDDEN_NAME", node.id, line))
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            violations.append(Violation("FORBIDDEN_ATTRIBUTE", f".{node.attr}", line))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for url in _URL.findall(node.value):
                if not (sut_url and url.startswith(sut_url.rstrip("/"))):
                    violations.append(Violation("HARDCODED_URL", url, line))
    return violations


def check_files(workspace: Path, paths: Iterable[str], *, sut_url: str | None = None) -> list[tuple[str, Violation]]:
    found = []
    for rel in paths:
        path = workspace / rel
        if path.is_file():
            found += [(rel, v) for v in check_source(path.read_text(encoding="utf-8", errors="replace"), sut_url=sut_url)]
    return found
