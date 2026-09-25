import pytest

def test_tc1_project_member_can_read_task_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]
    
    # Read task detail as alice (project member/owner)
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid
    assert get_res.json()["title"] == "Task 1"

def test_tc2_non_project_member_receives_403(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]
    
    # Read task detail as bob (non-member)
    bob = as_user("bob")
    get_res = bob.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 403, get_res.text

def test_tc3_non_existent_task_receives_404(as_user):
    alice = as_user("alice")
    get_res = alice.get("/api/tasks/999999")
    assert get_res.status_code == 404, get_res.text
