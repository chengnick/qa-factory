"""REQ-005: done is a terminal state."""


def test_done_task_cannot_move_back_to_in_progress(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "ship it"}).json()["id"]
    for to in ("in_progress", "done"):
        assert alice.post(f"/api/tasks/{tid}/transition", json={"to": to}).status_code == 200

    resp = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})

    assert resp.status_code == 409, resp.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"
