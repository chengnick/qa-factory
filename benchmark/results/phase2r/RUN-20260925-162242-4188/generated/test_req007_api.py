import pytest

def test_project_member_can_read_task_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "T1"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == tid
    assert r.json()["title"] == "T1"

def test_non_project_member_forbidden_reading_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "T1"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    bob = as_user("bob")
    r = bob.get(f"/api/tasks/{tid}")
    assert r.status_code == 403, r.text

def test_reading_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    r = alice.get("/api/tasks/non-existent-tid")
    assert r.status_code == 404, r.text
