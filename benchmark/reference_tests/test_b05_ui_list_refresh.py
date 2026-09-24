"""REQ-004: a task created through the form shows up in the list without a page reload."""

import uuid

import pytest
from playwright.sync_api import expect


@pytest.mark.ui
def test_created_task_appears_without_reload(base_url, new_project, page):
    pid = new_project(owner="alice")
    title = f"ui task {uuid.uuid4().hex[:6]}"
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    expect(page.get_by_test_id("task-item")).to_have_count(0)

    with page.expect_response(lambda r: r.request.method == "POST" and f"/api/projects/{pid}/tasks" in r.url) as created:
        page.get_by_test_id("new-title").fill(title)
        page.get_by_test_id("create-btn").click()
    assert created.value.status == 201

    expect(page.get_by_test_id("task-title")).to_have_text([title], timeout=2000)
