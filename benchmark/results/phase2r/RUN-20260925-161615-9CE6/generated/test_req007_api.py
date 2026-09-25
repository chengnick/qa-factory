import pytest

def test_project_member_can_read_task_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    task_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert task_resp.status_code == 201, task_resp.text
    tid = task_resp.json()["id"]
    
    get_resp = alice.get(f"/api/tasks/{tid}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["title"] == "Task 1"

def test_non_project_member_gets_403_reading_task_detail(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    task_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert task_resp.status_code == 201, task_resp.text
    tid = task_resp.json()["id"]
    
    get_resp = bob.get(f"/api/tasks/{tid}")
    assert get_resp.status_code == 403, get_resp.text

def test_getting_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    get_resp = alice.get("/api/tasks/99999")
    assert get_resp.status_code == 404, get_resp.text
