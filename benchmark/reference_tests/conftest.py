"""Black-box fixtures for reference tests.

The SUT runs as a real uvicorn process that inherits SUT_BUGS from this pytest process,
so the same tests run unchanged against every bug configuration. Set SUT_BASE_URL to
test an already-running SUT instead.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_S = 15


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(url: str, proc: subprocess.Popen | None, log: Path | None = None) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            out = log.read_text(encoding="utf-8", errors="replace") if log else ""
            raise RuntimeError(f"SUT exited during startup (code {proc.returncode}):\n{out}")
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"SUT at {url} not healthy after {STARTUP_TIMEOUT_S}s")


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    external = os.environ.get("SUT_BASE_URL")
    if external:
        _wait_healthy(external.rstrip("/"), None)
        yield external.rstrip("/")
        return
    port = _free_port()
    # Log to a file, not a PIPE: an unread PIPE fills up on 500 tracebacks and blocks the server.
    log_dir = tempfile.TemporaryDirectory(prefix="sut-")
    log = Path(log_dir.name) / "sut.log"
    log_fh = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sut.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO_ROOT,
        env={**os.environ, "SUT_DB": ":memory:"},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(url, proc, log)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()
        log_dir.cleanup()


@pytest.fixture(scope="session")
def as_user(base_url: str) -> Iterator[Callable[[str], httpx.Client]]:
    """as_user("alice") -> httpx.Client that sends X-User: alice."""
    clients: dict[str, httpx.Client] = {}

    def get(username: str) -> httpx.Client:
        if username not in clients:
            clients[username] = httpx.Client(base_url=base_url, headers={"X-User": username}, timeout=10)
        return clients[username]

    yield get
    for c in clients.values():
        c.close()


@pytest.fixture(scope="session")
def user_ids(base_url: str) -> dict[str, int]:
    return {u["username"]: u["id"] for u in httpx.get(f"{base_url}/api/users").json()}


@pytest.fixture
def new_project(as_user, user_ids) -> Callable[..., int]:
    """new_project(owner="alice", members=("bob",)) -> project id; a fresh project per call for isolation."""

    def create(owner: str = "alice", members: tuple[str, ...] = ()) -> int:
        resp = as_user(owner).post("/api/projects", json={"name": f"ref-{uuid.uuid4().hex[:8]}"})
        assert resp.status_code == 201, resp.text
        pid = resp.json()["id"]
        for m in members:
            r = as_user(owner).post(f"/api/projects/{pid}/members", json={"user_id": user_ids[m]})
            assert r.status_code == 201, r.text
        return pid

    return create


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.set_default_timeout(5000)
    yield pg
    ctx.close()
