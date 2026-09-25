import pytest

def test_project_member_can_read_task_detail(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    
    # Create a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert create_res.status_code == 201, create_res.text
    task = create_res.json()
    tid = task["id"]
    
    # Read task detail as project member (alice)
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid
    assert get_res.json()["title"] == "Test Task"

def test_non_project_member_forbidden_reading_task_detail(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    bob = as_user("bob")
    
    # Alice creates a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice's Task"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]
    
    # Bob tries to read the task detail
    get_res = bob.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 403, get_res.text

def test_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    get_res = alice.get("/api/tasks/99999")
    assert get_res.status_code == 404, get_res.text
