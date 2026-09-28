import pytest

def test_assign_task_non_project_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r_task.status_code == 201, r_task.text
    task = r_task.json()
    tid = task["id"]
    
    # Try to assign task to bob who is not a project member
    bob_id = user_ids["bob"]
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": bob_id})
    assert r_patch.status_code == 422, r_patch.text
    
    # Verify assignee remains unchanged (None)
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["assignee_id"] is None

def test_assign_task_non_existent_user(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r_task.status_code == 201, r_task.text
    task = r_task.json()
    tid = task["id"]
    
    # Try to assign task to a non-existent user id
    non_existent_id = 999999
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": non_existent_id})
    assert r_patch.status_code == 422, r_patch.text
