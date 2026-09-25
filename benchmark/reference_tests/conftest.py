"""Black-box fixtures for reference tests.

The SUT runs as a real uvicorn process that inherits SUT_BUGS from this pytest process,
so the same tests run unchanged against every bug configuration. Set SUT_BASE_URL to
test an already-running SUT instead.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator

import httpx
import pytest

from sut.launcher import running_sut, wait_healthy


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    external = os.environ.get("SUT_BASE_URL")
    if external:
        wait_healthy(external)
        yield external.rstrip("/")
        return
    with running_sut() as url:
        yield url


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
