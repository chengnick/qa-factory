from playwright.sync_api import expect

def test_req004_tc1_query_string_preselects_user_and_project(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    user_select = page.get_by_test_id("user-select")
    project_select = page.get_by_test_id("project-select")

    expect(user_select).to_have_value("alice")
    expect(project_select).to_have_value(str(pid))


def test_req004_tc2_task_title_html_escaped(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    page.get_by_test_id("new-title").fill("<b>x</b>")
    page.get_by_test_id("create-btn").click()

    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("<b>x</b>")


def test_req004_tc3_task_creation_updates_list_instantly(page, base_url, new_project):
    pid = new_project(owner="alice")
    page.goto(f"{base_url}/?user=alice&project={pid}")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    page.get_by_test_id("new-title").fill("Instant Task")
    page.get_by_test_id("create-btn").click()

    task_list = page.get_by_test_id("task-list")
    expect(task_list).to_contain_text("Instant Task")


def test_req004_tc4_api_error_displays_message(page, base_url):
    page.goto(f"{base_url}/?user=alice&project=999999")
    expect(page.locator("body")).to_have_attribute("data-ready", "true")

    error_area = page.get_by_test_id("error")
    expect(error_area).not_to_be_empty()
