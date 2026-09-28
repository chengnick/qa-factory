import pytest
from playwright.sync_api import expect

def test_tc1_create_task_updates_list_instantly(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("Instant Task")
    page.get_by_test_id("create-btn").click()
    
    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("Instant Task")

def test_tc2_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    task_title_el = page.get_by_test_id("task-title")
    expect(task_title_el).to_have_text("<b>x</b>")
    
    # Verify innerHTML does not contain an actual <b> tag
    inner_html = task_title_el.inner_html()
    assert "<b>" not in inner_html, f"Expected no <b> tag in innerHTML, got: {inner_html}"

def test_tc3_api_errors_displayed(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=9999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_el = page.get_by_test_id("error")
    expect(error_el).to_be_visible()
    expect(error_el).not_to_have_text("")
