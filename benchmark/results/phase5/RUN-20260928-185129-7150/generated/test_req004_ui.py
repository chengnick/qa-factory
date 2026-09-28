from playwright.sync_api import expect

def test_tc1_pre_select_user_and_project(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    user_select = page.get_by_test_id("user-select")
    project_select = page.get_by_test_id("project-select")
    
    assert user_select.input_value() == "alice" or user_select.inner_text() == "alice" or user_select.evaluate("el => el.value") == "alice"
    assert str(project_select.evaluate("el => el.value")) == str(pid)

def test_tc2_instant_task_list_update(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("New UI Task")
    page.get_by_test_id("create-btn").click()
    
    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("New UI Task")

def test_tc3_render_task_title_as_plain_text_xss(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    xss_payload = "<script>alert(1)</script>"
    page.get_by_test_id("new-title").fill(xss_payload)
    page.get_by_test_id("create-btn").click()
    
    task_title_elem = page.get_by_test_id("task-title").first
    expect(task_title_elem).to_have_text(xss_payload)

def test_tc4_display_error_message_upon_api_error(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=99999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
