import pytest

def test_assign_task_to_non_project_member(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Try to assign to dave who is not a project member
    dave_id = user_ids["dave"]
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": dave_id})
    assert r_patch.status_code == 422, r_patch.text
    
    # Verify assignee remains unchanged (None)
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["assignee_id"] is None


def test_assign_task_to_non_existent_user(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Try to assign to a non-existent user ID
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": 999999})
    assert r_patch.status_code == 422, r_patch.text


def test_unassign_task_by_passing_null(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob_id = user_ids["bob"]
    pid = new_project(owner="alice", members=("bob",))
    
    # Create task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 3"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Assign to bob first
    r_assign = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": bob_id})
    assert r_assign.status_code == 200, r_assign.text
    assert r_assign.json()["assignee_id"] == bob_id
    
    # Unassign by passing null
    r_unassign = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": None})
    assert r_unassign.status_code == 200, r_unassign.text
    assert r_unassign.json()["assignee_id"] is None
