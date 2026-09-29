from playwright.sync_api import expect

def test_tc1_create_task_updates_list(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("Instant Task")
    page.get_by_test_id("create-btn").click()
    
    task_item = page.get_by_test_id("task-item")
    expect(task_item).to_be_visible()
    expect(page.get_by_test_id("task-title").first).to_have_text("Instant Task")

def test_tc2_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()
    
    title_el = page.get_by_test_id("task-title").first
    expect(title_el).to_have_text("<b>x</b>")
    # Ensure it's rendered as text, not HTML element
    assert title_el.locator("b").count() == 0

def test_tc3_api_errors_display_message(page, base_url, new_project):
    pid = new_project(owner="alice", members=())
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    page.get_by_test_id("new-title").fill("")
    page.get_by_test_id("create-btn").click()
    
    error_el = page.get_by_test_id("error")
    expect(error_el).not_to_be_empty()
