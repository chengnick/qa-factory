"""REQ-006: a task can only be assigned to a project member."""


def test_cannot_assign_task_to_non_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "unassigned"}).json()["id"]

    resp = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": user_ids["dave"]})

    assert resp.status_code == 422, resp.text
    assert alice.get(f"/api/tasks/{tid}").json()["assignee_id"] is None
