import pytest

def test_assign_task_to_non_project_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task in the project
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r_task.status_code == 201, r_task.text
    task = r_task.json()
    tid = task["id"]
    original_assignee = task.get("assignee_id")

    # Try to assign to a non-project member (bob exists, but is not a member of alice's new project)
    bob_id = user_ids["bob"]
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": bob_id})
    assert r_patch.status_code == 422, r_patch.text

    # Verify the task's assignee remains unchanged
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["assignee_id"] == original_assignee, r_get.text


def test_assign_task_to_non_existent_user(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task in the project
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]

    # Try to assign to a non-existent user ID
    non_existent_id = 88888
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": non_existent_id})
    assert r_patch.status_code == 422, r_patch.text
