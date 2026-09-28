import pytest

def test_req007_tc1_project_member_can_read_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Alice creates a task
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Alice reads task details
    res = alice.get(f"/api/tasks/{tid}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == tid
    assert data["title"] == "Test Task"

def test_req007_tc2_non_member_forbidden_task_details(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    # Alice creates a task
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Bob (non-project member) tries to read task details
    res = bob.get(f"/api/tasks/{tid}")
    assert res.status_code == 403, res.text

def test_req007_tc3_non_existent_task_returns_404(as_user, new_project):
    alice = as_user("alice")
    # Create a project just to ensure valid user context if needed, though not strictly required for 404 on task
    new_project(owner="alice", members=())
    
    res = alice.get("/api/tasks/99999")
    assert res.status_code == 404, res.text
