import pytest

def test_project_member_can_read_task_details(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    data = get_res.json()
    assert data["id"] == tid
    assert data["title"] == "Test Task"

def test_non_project_member_receives_403(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    get_res = bob.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 403, get_res.text

def test_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    get_res = alice.get("/api/tasks/999999")
    assert get_res.status_code == 404, get_res.text
