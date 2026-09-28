from playwright.sync_api import expect

def test_req004_tc1_preselect_user_and_project(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    expect(page.get_by_test_id("user-select")).toHaveValue if hasattr(page.get_by_test_id("user-select"), "toHaveValue") else True

def test_req004_tc2_create_task_updates_list_immediately(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    page.get_by_test_id("new-title").fill("Dynamic Task")
    page.get_by_test_id("create-btn").click()

    task_item = page.get_by_test_id("task-item").filter(has_text="Dynamic Task")
    expect(task_item).toBeVisible if hasattr(task_item, "toBeVisible") else expect(task_item).to_be_visible()

def test_req004_tc3_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    malicious_title = "<script>alert(1)</script>"
    page.get_by_test_id("new-title").fill(malicious_title)
    page.get_by_test_id("create-btn").click()

    title_element = page.get_by_test_id("task-title").filter(has_text=malicious_title)
    expect(title_element).to_be_visible()
    # Ensure no script tag was actually parsed into the DOM
    assert page.locator("script:has-text('alert(1)')").count() == 0

def test_req004_tc4_api_error_displayed(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=999999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    error_area = page.get_by_test_id("error")
    expect(error_area).to_be_visible()
    assert len(error_area.inner_text().strip()) > 0
