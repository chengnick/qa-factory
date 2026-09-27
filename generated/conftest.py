"""Owner-maintained fixtures for agent-generated tests. Read-only for agents.

Generated tests run against an already-running SUT at $SUT_BASE_URL (set by the pytest tool).
They never start servers or import the SUT; they only talk HTTP / drive the browser.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Keep each phase's report on the test item, so the page fixture knows at teardown whether the test failed."""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"_qa_report_{report.when}", report)


def _failed(item) -> bool:
    return any(getattr(getattr(item, f"_qa_report_{when}", None), "failed", False) for when in ("setup", "call"))


def _evidence_dir(item) -> Path | None:
    """$QA_PLAYWRIGHT_DIR/{test name}; None when the pytest tool did not ask for evidence."""
    root = os.environ.get("QA_PLAYWRIGHT_DIR")
    if not root:
        return None
    return Path(root) / re.sub(r"[^A-Za-z0-9_.-]+", "_", item.name)[:100]


@pytest.fixture
def page(browser, request):
    """A fresh Playwright Page (sync API), 5s default timeout.

    Evidence (spec v3 §4.2): when a test fails, trace.zip, screenshot.png and console.log are saved to
    $QA_PLAYWRIGHT_DIR/{test name}/. Passing tests keep nothing.
    """
    context = browser.new_context()
    evidence = _evidence_dir(request.node)
    if evidence is not None:
        context.tracing.start(screenshots=True, snapshots=True)
    pg = context.new_page()
    console: list[str] = []
    pg.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))
    pg.on("pageerror", lambda exc: console.append(f"[pageerror] {exc}"))
    pg.set_default_timeout(5000)
    yield pg
    if evidence is not None and _failed(request.node):
        evidence.mkdir(parents=True, exist_ok=True)
        try:
            pg.screenshot(path=str(evidence / "screenshot.png"), full_page=True)
        except Exception as exc:  # a crashed page still gets its trace and console log
            console.append(f"[evidence] screenshot failed: {type(exc).__name__}: {exc}")
        context.tracing.stop(path=str(evidence / "trace.zip"))
        (evidence / "console.log").write_text("\n".join(console) + "\n", encoding="utf-8")
    elif evidence is not None:
        context.tracing.stop()
    context.close()
