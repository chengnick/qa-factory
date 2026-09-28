from playwright.sync_api import expect

def test_tc1_create_task_updates_list_without_reload(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("Test Task")
    page.get_by_test_id("create-btn").click()
    
    task_item = page.get_by_test_id("task-item")
    expect(task_item).to_be_visible()
    expect(page.get_by_test_id("task-title")).to_contain_text("Test Task")

def test_tc2_task_title_with_html_rendered_as_literal(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    html_title = "<b>Bold Title</b>"
    page.get_by_test_id("new-title").fill(html_title)
    page.get_by_test_id("create-btn").click()
    
    task_title_el = page.get_by_test_id("task-title")
    expect(task_title_el).to_be_visible()
    expect(task_title_el).not_to_have_JS_property("innerHTML", lambda val: "<b>" in val)
    expect(task_title_el).to_have_text(html_title)

def test_tc3_api_error_displays_message_in_error_area(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=99999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_area = page.get_by_test_id("error")
    expect(error_area).to_be_visible()
    expect(error_area).not_to_have_text("")
