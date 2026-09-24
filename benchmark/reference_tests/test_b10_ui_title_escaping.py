"""REQ-004: task titles are displayed as plain text, never parsed as HTML."""

import pytest
from playwright.sync_api import expect

MARKUP_TITLE = '<b data-testid="injected">bold</b>'


@pytest.mark.ui
def test_title_markup_is_rendered_as_text(base_url, as_user, new_project, page):
    pid = new_project(owner="alice")
    assert as_user("alice").post(f"/api/projects/{pid}/tasks", json={"title": MARKUP_TITLE}).status_code == 201

    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    expect(page.get_by_test_id("task-title")).to_have_text([MARKUP_TITLE])
    expect(page.get_by_test_id("injected")).to_have_count(0)
