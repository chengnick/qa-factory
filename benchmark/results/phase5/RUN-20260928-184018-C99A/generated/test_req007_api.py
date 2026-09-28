import pytest

def test_tc1_project_member_can_read_task_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    res = alice.get(f"/api/tasks/{tid}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == tid
    assert data["title"] == "Test Task"

def test_tc2_non_project_member_cannot_read_task_detail(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice's Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    res = bob.get(f"/api/tasks/{tid}")
    assert res.status_code == 403, res.text

def test_tc3_reading_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    res = alice.get("/api/tasks/999999")
    assert res.status_code == 404, res.text
