"""REQ-008: only the project owner or the task creator may delete a task."""


def test_other_member_cannot_delete_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob", "carol"))
    tid = as_user("carol").post(f"/api/projects/{pid}/tasks", json={"title": "carol's task"}).json()["id"]

    resp = as_user("bob").delete(f"/api/tasks/{tid}")

    assert resp.status_code == 403, resp.text
    assert as_user("alice").get(f"/api/tasks/{tid}").status_code == 200
