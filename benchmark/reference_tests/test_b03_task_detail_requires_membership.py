"""REQ-007: task detail is readable only by project members."""


def test_non_member_cannot_read_task_detail(as_user, new_project):
    pid = new_project(owner="alice")
    tid = as_user("alice").post(f"/api/projects/{pid}/tasks", json={"title": "private"}).json()["id"]

    resp = as_user("bob").get(f"/api/tasks/{tid}")

    assert resp.status_code == 403, resp.text
