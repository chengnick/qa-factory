from playwright.sync_api import expect

def test_tc1_create_task_successfully_via_form(base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("New UI Task")
    page.get_by_test_id("create-btn").click()
    
    task_item = page.get_by_test_id("task-item").filter(has_text="New UI Task")
    expect(task_item).to_be_visible()

def test_tc2_task_title_html_tags_as_literal(base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    html_title = "<b>Bold Title</b>"
    page.get_by_test_id("new-title").fill(html_title)
    page.get_by_test_id("create-btn").click()
    
    task_item = page.get_by_test_id("task-item").filter(has_text=html_title)
    expect(task_item).to_be_visible()
    
    # Verify that the <b> tag was not parsed as HTML
    bold_element = page.locator("b", has_text="Bold Title")
    assert bold_element.count() == 0 or not bold_element.is_visible(), "HTML tags should not be parsed"

def test_tc3_display_error_message_on_api_error(base_url):
    page.goto(f"{base_url}/?user=alice&project=99999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_area = page.get_by_test_id("error")
    expect(error_area).to_be_visible()
    expect(error_area).not_to_be_empty()
