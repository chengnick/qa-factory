"""pytest / playwright tools: run generated tests in a subprocess against the SUT.

`playwright` is the same runner restricted to UI test files; the browser is driven by the
Playwright fixtures in generated/conftest.py.

Isolation (see README): the subprocess runs in the per-run workspace with its own pytest.ini, and gets
only whitelisted environment variables, so secrets such as GEMINI_API_KEY and PYTHONPATH never reach
generated code (L0+). With isolation="L1" (the default) it also installs tools/l1_guard.py, an audit hook
that limits writes to this call's own files, network to the SUT and processes to the Playwright driver.
That guard is an in-process check, not an OS sandbox (tools/l1_guard.py says what it cannot stop).
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tools.file_tool import resolve_generated
from observability.redact import redact
from tools.code_policy import check_files
from tools.registry import PermissionDeniedError, ToolArgumentError, ToolResult, ToolTimeoutError
from tools.workspace import ensure_pytest_ini

STDOUT_LIMIT = 20_000
REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = Path(__file__).resolve().with_name("l1_guard.py")
ISOLATION_LEVELS = ("L0+", "L1")
# Runs in the child: import pytest and the libraries tests may use (on Windows colorama, click and others load
# system DLLs through ctypes at import, which the guard refuses afterwards), load the guard by path (the repo
# never goes on sys.path), install it, then run pytest. platform.platform() fills platform's cache first: on Windows
# it would otherwise start `cmd /c ver` from inside the test run.
PRELOAD = ("colorama", "httpx", "trio")  # trio (pulled in by the HTTP stack when installed) probes libc at import
BOOT = (
    "import importlib.util as u, json, platform, sys; import pytest; platform.platform(); "
    "[__import__(n) for n in {preload!r} if u.find_spec(n.split('.')[0])]; "
    "s = u.spec_from_file_location('qa_l1_guard', {guard!r}); m = u.module_from_spec(s); s.loader.exec_module(m); "
    "m.install(json.loads({config!r})); del u, s, m; "
    "sys.exit(pytest.main(sys.argv[1:]))"
)


def playwright_driver_dir() -> Path | None:
    try:
        import playwright
    except ImportError:
        return None
    return Path(playwright.__file__).resolve().parent / "driver"


def guard_config(*, sut_url: str, write: list[Path], log: Path) -> dict[str, Any]:
    parts = urlsplit(sut_url)
    driver = playwright_driver_dir()
    return {
        "write": [str(p) for p in write],
        "deny_read": [str(REPO_ROOT / ".env")],
        "exec": [str(driver)] if driver else [],
        "sut_host": parts.hostname or "",
        "sut_port": parts.port or (443 if parts.scheme == "https" else 80),
        "log": str(log),
    }


def read_denials(log: Path) -> list[dict[str, str]]:
    if not log.is_file():
        return []
    denials = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            denials.append({k: str(entry.get(k, "")) for k in ("event", "target", "reason")})
    return denials

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


def subprocess_env(sut_url: str, evidence_dir: Path | None = None) -> dict[str, str]:
    env = {name: os.environ[name] for name in ENV_WHITELIST if name in os.environ}
    if evidence_dir is not None:  # read by the page fixture in generated/conftest.py
        env["QA_PLAYWRIGHT_DIR"] = str(evidence_dir)
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
    def __init__(
        self,
        root: Path,
        sut_url: str,
        *,
        timeout_s: float = 120.0,
        enforce_policy: bool = True,
        policy: Any = None,
        evidence: bool = False,
        isolation: str = "L1",
    ) -> None:
        if isolation not in ISOLATION_LEVELS:
            raise ValueError(f"isolation must be one of {ISOLATION_LEVELS}, got {isolation!r}")
        self.root = root  # the run workspace
        self.isolation = isolation
        self.sut_url = sut_url
        self.timeout_s = timeout_s
        # Tests of the isolation layer itself switch the code policy off to probe the environment directly.
        self.enforce_policy = enforce_policy
        self.policy = policy  # None -> the default policy file
        # Playwright evidence of failed UI tests goes to playwright/{junit stem}/{test}/ (one folder per call).
        self.evidence = evidence

    def __call__(self, paths: list[str]) -> ToolResult:
        if not paths:
            raise ToolArgumentError("paths must not be empty")
        files = [resolve_generated(self.root, p) for p in paths]
        missing = [p for p, f in zip(paths, files) if not f.is_file()]
        if missing:
            raise ToolArgumentError(f"test files not found: {missing}")
        rel = [f.relative_to(self.root).as_posix() for f in files]
        # Defence in depth: the gate checks this for agents; evaluation builds call the tool directly.
        if self.enforce_policy and (violations := check_files(self.root, rel, sut_url=self.sut_url, policy=self.policy)):
            detail = "; ".join(f"{p}:{v.line} {v.kind} {v.detail}" for p, v in violations)
            raise PermissionDeniedError(f"generated-code policy: {detail}")

        # junit reports are kept in the workspace as run evidence (never deleted).
        reports = self.root / "reports"
        reports.mkdir(exist_ok=True)
        junit = reports / f"junit-{Path(rel[0]).stem}-{secrets.token_hex(3)}.xml"
        call = junit.stem.removeprefix("junit-")
        evidence_dir = self.root / "playwright" / call if self.evidence else None
        ini = ensure_pytest_ini(self.root)
        args = [*rel, "-q", "-p", "no:cacheprovider", "-c", str(ini), "--rootdir", str(self.root), f"--junitxml={junit}"]
        env = subprocess_env(self.sut_url, evidence_dir)
        guard_log = reports / f"l1-{call}.log"
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True)  # created here: under L1 the child may write inside it, not create it
        if self.isolation == "L1":
            # A private temp dir per call: the guard lets the test write there, not in the shared system temp.
            private_tmp = self.root / "tmp" / call
            private_tmp.mkdir(parents=True)
            env.update(dict.fromkeys(("TEMP", "TMP", "TMPDIR"), str(private_tmp)))  # all three are whitelisted names
            write = [junit, guard_log, private_tmp, *([evidence_dir] if evidence_dir else [])]
            config = json.dumps(guard_config(sut_url=self.sut_url, write=write, log=guard_log))
            preload = [*PRELOAD, *(["playwright.sync_api"] if self.evidence else [])]
            cmd = [sys.executable, "-B", "-c", BOOT.format(guard=str(GUARD), config=config, preload=preload), *args]
        else:
            cmd = [sys.executable, "-m", "pytest", *args]
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.root,
                env=env,
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
        data["isolation"] = self.isolation
        if denials := read_denials(guard_log):
            data["l1_denials"] = denials
        if evidence_dir is not None and evidence_dir.is_dir():
            data["evidence"] = sorted(d.relative_to(self.root).as_posix() for d in evidence_dir.iterdir() if d.is_dir())
        return ToolResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=output,
            command="pytest " + " ".join(rel),
            data=data,
        )
