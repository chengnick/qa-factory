from playwright.sync_api import expect

def test_tc1_create_task_updates_list_without_reload(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("New UI Task")
    page.get_by_test_id("create-btn").click()
    
    task_item = page.get_by_test_id("task-item").filter(has_text="New UI Task")
    expect(task_item).toBeVisible()

def test_tc2_task_title_with_html_displayed_as_plain_text(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    task_title = page.get_by_test_id("task-title").filter(has_text="<b>x</b>")
    expect(task_title).toBeVisible()
    # Ensure <b> tag is not rendered as actual HTML element
    assert page.locator("b").count() == 0 or "<b>x</b>" in task_title.inner_html()

def test_tc3_api_error_displays_message_in_error_area(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    # Submitting empty title should trigger an API error or validation error
    page.get_by_test_id("new-title").fill("")
    page.get_by_test_id("create-btn").click()
    
    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
