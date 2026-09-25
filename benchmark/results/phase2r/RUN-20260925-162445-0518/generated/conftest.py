"""Owner-maintained fixtures for agent-generated tests. Read-only for agents.

Generated tests run against an already-running SUT at $SUT_BASE_URL (set by the pytest tool).
They never start servers or import the SUT; they only talk HTTP / drive the browser.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator

import httpx
import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.environ.get("SUT_BASE_URL")
    if not url:
        pytest.exit("SUT_BASE_URL is not set; generated tests must run through the pytest tool", returncode=4)
    return url.rstrip("/")


@pytest.fixture(scope="session")
def as_user(base_url: str) -> Iterator[Callable[[str], httpx.Client]]:
    """as_user("alice") -> httpx.Client with base_url set and the X-User header for that user."""
    clients: dict[str, httpx.Client] = {}

    def get(username: str) -> httpx.Client:
        if username not in clients:
            clients[username] = httpx.Client(base_url=base_url, headers={"X-User": username}, timeout=10)
        return clients[username]

    yield get
    for client in clients.values():
        client.close()


@pytest.fixture(scope="session")
def user_ids(base_url: str) -> dict[str, int]:
    """{"alice": 1, ...} as reported by GET /api/users."""
    return {u["username"]: u["id"] for u in httpx.get(f"{base_url}/api/users", timeout=10).json()}


@pytest.fixture
def new_project(as_user, user_ids) -> Callable[..., int]:
    """new_project(owner="alice", members=("bob",)) -> id of a brand-new project owned by `owner`."""

    def create(owner: str = "alice", members: tuple[str, ...] = ()) -> int:
        resp = as_user(owner).post("/api/projects", json={"name": f"gen-{uuid.uuid4().hex[:8]}"})
        assert resp.status_code == 201, f"fixture could not create project: {resp.status_code} {resp.text}"
        pid = resp.json()["id"]
        for member in members:
            r = as_user(owner).post(f"/api/projects/{pid}/members", json={"user_id": user_ids[member]})
            assert r.status_code == 201, f"fixture could not add member {member}: {r.status_code} {r.text}"
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
    """A fresh Playwright Page (sync API), 5s default timeout."""
    context = browser.new_context()
    pg = context.new_page()
    pg.set_default_timeout(5000)
    yield pg
    context.close()
