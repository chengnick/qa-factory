"""Start the SUT as a real uvicorn process (used by reference tests and by the pipeline).

Standard library only, so the SUT package keeps its own small dependency set.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTUP_TIMEOUT_S = 15.0


class SUTStartupError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_healthy(url: str, timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=timeout_s) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_healthy(url: str, proc: subprocess.Popen | None = None, log: Path | None = None, timeout_s: float = STARTUP_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            out = log.read_text(encoding="utf-8", errors="replace") if log else ""
            raise SUTStartupError(f"SUT exited during startup (code {proc.returncode}):\n{out}")
        if is_healthy(url):
            return
        time.sleep(0.1)
    raise SUTStartupError(f"SUT at {url} not healthy after {timeout_s}s")


@contextmanager
def running_sut(bugs: Sequence[str] | None = None, *, port: int | None = None) -> Iterator[str]:
    """Yield the base URL of a fresh SUT. `bugs=None` inherits SUT_BUGS from the environment.

    Output goes to a temp log file, never an unread PIPE: a full pipe blocks the server on 500 tracebacks.
    """
    env = {**os.environ, "SUT_DB": ":memory:"}
    if bugs is not None:
        env["SUT_BUGS"] = ",".join(bugs)
    port = port or free_port()
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="sut-") as log_dir:
        log = Path(log_dir) / "sut.log"
        with log.open("w", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "sut.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=REPO_ROOT,
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            try:
                wait_healthy(url, proc, log)
                yield url
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
