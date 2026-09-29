import pytest

def test_assign_task_to_non_project_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]
    
    # Try to assign to bob who is not a project member
    bob_id = user_ids["bob"]
    patch_res = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": bob_id})
    assert patch_res.status_code == 422, patch_res.text
    
    # Verify assignee remains unchanged (None)
    get_res = alice.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["assignee_id"] is None, get_res.text

def test_assign_task_to_non_existent_user(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]
    
    # Try to assign to a non-existent user ID
    non_existent_id = 999999
    patch_res = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": non_existent_id})
    assert patch_res.status_code == 422, patch_res.text
