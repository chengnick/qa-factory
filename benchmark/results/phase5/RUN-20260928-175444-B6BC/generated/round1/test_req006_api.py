import pytest
import httpx

def test_tc1_assign_task_to_non_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task in the project
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert r_task.status_code == 201, r_task.text
    task_id = r_task.json()["id"]
    
    # Bob is not a project member
    bob_id = user_ids["bob"]
    
    # Try to assign task to bob
    r_patch = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": bob_id})
    assert r_patch.status_code == 422, r_patch.text
    
    # Verify assignee remains unchanged (None)
    r_get = alice.get(f"/api/tasks/{task_id}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["assignee_id"] is None, r_get.text

def test_tc2_assign_task_to_non_existent_user(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task in the project
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert r_task.status_code == 201, r_task.text
    task_id = r_task.json()["id"]
    
    # Non-existent user ID
    non_existent_id = 99999
    
    # Try to assign task to non-existent user
    r_patch = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": non_existent_id})
    assert r_patch.status_code == 422, r_patch.text
