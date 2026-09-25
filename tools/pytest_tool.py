"""pytest / playwright tools: run generated tests in a subprocess against the SUT.

`playwright` is the same runner restricted to UI test files; the browser is driven by the
Playwright fixtures in generated/conftest.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from tools.file_tool import resolve_generated
from tools.registry import ToolArgumentError, ToolResult, ToolTimeoutError

STDOUT_LIMIT = 20_000


def _junit_counts(path: Path) -> dict[str, int]:
    """Suite totals, plus failures split into assertion failures vs. other exceptions raised by test code."""
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "assertion_failures": 0, "exception_failures": 0}
    if not path.exists():
        return counts
    root = ET.parse(path).getroot()
    for suite in root.iter("testsuite"):
        for key in ("tests", "failures", "errors", "skipped"):
            counts[key] += int(suite.get(key, 0))
    for failure in root.iter("failure"):
        message = failure.get("message", "")
        kind = "assertion_failures" if message.startswith("AssertionError") or message.startswith("assert ") else "exception_failures"
        counts[kind] += 1
    return counts


class PytestTool:
    def __init__(self, root: Path, sut_url: str, *, timeout_s: float = 120.0) -> None:
        self.root = root
        self.sut_url = sut_url
        self.timeout_s = timeout_s

    def __call__(self, paths: list[str]) -> ToolResult:
        if not paths:
            raise ToolArgumentError("paths must not be empty")
        files = [resolve_generated(self.root, p) for p in paths]
        missing = [p for p, f in zip(paths, files) if not f.is_file()]
        if missing:
            raise ToolArgumentError(f"test files not found: {missing}")
        rel = [f.relative_to(self.root).as_posix() for f in files]

        with tempfile.TemporaryDirectory(prefix="qa-pytest-") as tmp:
            junit = Path(tmp) / "junit.xml"
            cmd = [sys.executable, "-m", "pytest", *rel, "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"]
            # No host plugin autoload: faster, and generated tests run the same on every machine.
            env = {**os.environ, "SUT_BASE_URL": self.sut_url, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
            try:
                proc = subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True, timeout=self.timeout_s, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired as exc:
                raise ToolTimeoutError(f"pytest did not finish within {self.timeout_s:.0f}s") from exc
            counts = _junit_counts(junit)

        output = (proc.stdout + proc.stderr)[-STDOUT_LIMIT:]
        data: dict[str, Any] = {**counts, "files": rel}
        return ToolResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=output,
            command="pytest " + " ".join(rel),
            data=data,
        )
