import pytest
from playwright.sync_api import expect

def test_tc1_create_task_instantly(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true", timeout=10000)
    
    page.get_by_test_id("new-title").fill("Instant Update Task")
    page.get_by_test_id("create-btn").click()
    
    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("Instant Update Task")

def test_tc2_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true", timeout=10000)
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    task_title = page.get_by_test_id("task-title").first
    expect(task_title).to_have_text("<b>x</b>")

def test_tc3_display_error_message(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=999999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true", timeout=10000)
    
    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
