from playwright.sync_api import expect

def test_req004_tc1_url_params_preselect(base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")
    
    expect(page.get_by_test_id("user-select")).to_have_value("alice")
    expect(page.get_by_test_id("project-select")).to_have_value(str(pid))


def test_req004_tc2_task_creation_instant_display(base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    page.get_by_test_id("new-title").fill("Instant Task")
    page.get_by_test_id("create-btn").click()

    task_item = page.get_by_test_id("task-item")
    expect(task_item).to_be_visible()
    expect(page.get_by_test_id("task-title")).to_contain_text("Instant Task")


def test_req004_tc3_task_title_html_escaped(base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    payload = "<b>x</b>"
    page.get_by_test_id("new-title").fill(payload)
    page.get_by_test_id("create-btn").click()

    task_title_el = page.get_by_test_id("task-title")
    expect(task_title_el).to_contain_text(payload)
    # Ensure the <b> tag was not parsed into a real bold element (no <b> child with inner text 'x' rendered as element)
    assert task_title_el.locator("b").count() == 0, "HTML tag should not be parsed as an element"


def test_req004_tc4_api_error_message_displayed(base_url):
    page.goto(f"{base_url}/?user=alice&project=999999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
