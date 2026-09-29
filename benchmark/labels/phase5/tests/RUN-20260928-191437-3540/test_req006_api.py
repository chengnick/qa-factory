import pytest

def test_assign_task_to_non_project_member_returns_422(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]
    original_assignee = task_res.json().get("assignee_id")

    # Try to assign task to bob who is not a project member
    bob_id = user_ids["bob"]
    patch_res = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": bob_id})
    assert patch_res.status_code == 422, patch_res.text

    # Verify assignee remains unchanged
    get_res = alice.get(f"/api/tasks/{task_id}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["assignee_id"] == original_assignee

def test_assign_task_to_non_existent_user_returns_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]

    # Try to assign task to a non-existent user id
    patch_res = alice.patch(f"/api/tasks/{task_id}", json={"assignee_id": 99999})
    assert patch_res.status_code == 422, patch_res.text
