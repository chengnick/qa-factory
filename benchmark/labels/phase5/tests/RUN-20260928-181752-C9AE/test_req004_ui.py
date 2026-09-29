import pytest
from playwright.sync_api import expect

def test_req004_tc1_url_params_preselect(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    user_select = page.get_by_test_id("user-select")
    expect(user_select).to_have_value("alice")
    
    project_select = page.get_by_test_id("project-select")
    expect(project_select).to_have_value(str(pid))

def test_req004_tc2_task_creation_updates_list(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("New UI Test Task")
    page.get_by_test_id("create-btn").click()
    
    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("New UI Test Task")

def test_req004_tc3_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    task_title_el = page.get_by_test_id("task-title").first
    expect(task_title_el).to_have_text("<b>x</b>")
    assert task_title_el.locator("b").count() == 0, "HTML tag should not be rendered as an element"

def test_req004_tc4_api_errors_displayed(page, base_url):
    page.goto(f"{base_url}/?user=unknown_user&project=1")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
