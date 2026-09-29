from playwright.sync_api import expect

def test_tc1_create_task_updates_list(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("New UI Task")
    page.get_by_test_id("create-btn").click()
    
    task_title = page.get_by_test_id("task-title").first
    expect(task_title).to_have_text("New UI Task")

def test_tc2_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    task_title = page.get_by_test_id("task-title").first
    expect(task_title).to_have_text("<b>x</b>")
    # Ensure it's rendered as text and not as a <b> element
    assert task_title.locator("b").count() == 0, "HTML tags should not be parsed as elements"

def test_tc3_api_error_shows_message(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=99999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
