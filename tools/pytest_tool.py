"""pytest / playwright tools: run generated tests in a subprocess against the SUT.

`playwright` is the same runner restricted to UI test files; the browser is driven by the
Playwright fixtures in generated/conftest.py.

Isolation (partial L1, see README): the subprocess runs in the per-run workspace with its own
pytest.ini, and gets only whitelisted environment variables, so secrets such as GEMINI_API_KEY and
PYTHONPATH never reach generated code. There is no filesystem sandbox: generated code can still open
any path the OS user can read or write.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from tools.file_tool import resolve_generated
from observability.redact import redact
from tools.registry import ToolArgumentError, ToolResult, ToolTimeoutError
from tools.workspace import ensure_pytest_ini

STDOUT_LIMIT = 20_000

# The only variables passed through from the parent environment: what Python, the OS and the
# Playwright browser cache need to start. Everything else (API keys, tokens, PYTHONPATH) is dropped.
ENV_WHITELIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "PLAYWRIGHT_BROWSERS_PATH",
    "LANG",
    "LC_ALL",
    "TZ",
)


def subprocess_env(sut_url: str) -> dict[str, str]:
    env = {name: os.environ[name] for name in ENV_WHITELIST if name in os.environ}
    env.update(
        {
            "SUT_BASE_URL": sut_url,
            # No host plugin autoload: faster, and generated tests run the same on every machine.
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


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
        kind = "assertion_failures" if _is_assertion(message) else "exception_failures"
        counts[kind] += 1
    return counts


MESSAGE_LIMIT = 500


def _is_assertion(message: str) -> bool:
    return message.startswith("AssertionError") or message.startswith("assert ")


def _node_id(root: Path, classname: str, name: str) -> str:
    """junit (classname, name) -> pytest node id, e.g. ("generated.test_a.TestX", "test_y") -> generated/test_a.py::TestX::test_y."""
    if not classname:  # module-level error (collection failure): name is the dotted module
        return name.replace(".", "/") + ".py"
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        module = "/".join(parts[:cut]) + ".py"
        if (root / module).is_file():
            return "::".join([module, *parts[cut:], name])
    return "::".join([classname.replace(".", "/") + ".py", name])


def junit_tests(path: Path, root: Path) -> list[dict[str, str]]:
    """One entry per test case: node_id, outcome (PASS / FAIL / ERROR / SKIP) and a short redacted message.

    FAIL = failed with AssertionError; ERROR = any other exception, setup/teardown or collection error.
    """
    if not path.exists():
        return []
    results = []
    for case in ET.parse(path).getroot().iter("testcase"):
        failure, error, skipped = case.find("failure"), case.find("error"), case.find("skipped")
        if failure is not None:
            message = failure.get("message", "")
            outcome = "FAIL" if _is_assertion(message) else "ERROR"
        elif error is not None:
            message, outcome = error.get("message", "error"), "ERROR"
        elif skipped is not None:
            message, outcome = skipped.get("message", ""), "SKIP"
        else:
            message, outcome = "", "PASS"
        node = _node_id(root, case.get("classname", ""), case.get("name", ""))
        results.append({"node_id": node, "outcome": outcome, "message": redact(message)[:MESSAGE_LIMIT]})
    return results


class PytestTool:
    def __init__(self, root: Path, sut_url: str, *, timeout_s: float = 120.0) -> None:
        self.root = root  # the run workspace
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

        # junit reports are kept in the workspace as run evidence (never deleted).
        reports = self.root / "reports"
        reports.mkdir(exist_ok=True)
        junit = reports / f"junit-{Path(rel[0]).stem}-{secrets.token_hex(3)}.xml"
        ini = ensure_pytest_ini(self.root)
        cmd = [
            sys.executable, "-m", "pytest", *rel, "-q", "-p", "no:cacheprovider",
            "-c", str(ini), "--rootdir", str(self.root), f"--junitxml={junit}",
        ]  # fmt: skip
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.root,
                env=subprocess_env(self.sut_url),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolTimeoutError(f"pytest did not finish within {self.timeout_s:.0f}s") from exc
        counts = _junit_counts(junit)

        output = (proc.stdout + proc.stderr)[-STDOUT_LIMIT:]
        data: dict[str, Any] = {
            **counts,
            "files": rel,
            "junit": junit.relative_to(self.root).as_posix(),
            "results": junit_tests(junit, self.root),
        }
        return ToolResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=output,
            command="pytest " + " ".join(rel),
            data=data,
        )
