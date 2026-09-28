import pytest

def test_tc1_project_member_can_read_task_detail(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    
    # Create a task as alice
    create_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert create_resp.status_code == 201, create_resp.text
    task_id = create_resp.json()["id"]
    
    # Read task detail as alice
    get_resp = alice.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["id"] == task_id
    assert get_resp.json()["title"] == "Test Task"

def test_tc2_non_member_receives_403_reading_task_detail(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    bob = as_user("bob")
    
    # Create a task as alice
    create_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert create_resp.status_code == 201, create_resp.text
    task_id = create_resp.json()["id"]
    
    # Try to read task detail as bob (non-member)
    get_resp = bob.get(f"/api/tasks/{task_id}")
    assert get_resp.status_code == 403, get_resp.text

def test_tc3_non_member_receives_403_reading_project_tasks(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    bob = as_user("bob")
    
    # Create a task as alice
    create_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task for project"})
    assert create_resp.status_code == 201, create_resp.text
    
    # Try to list project tasks as bob (non-member)
    get_resp = bob.get(f"/api/projects/{pid}/tasks")
    assert get_resp.status_code == 403, get_resp.text

def test_tc4_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    get_resp = alice.get("/api/tasks/999999")
    assert get_resp.status_code == 404, get_resp.text
