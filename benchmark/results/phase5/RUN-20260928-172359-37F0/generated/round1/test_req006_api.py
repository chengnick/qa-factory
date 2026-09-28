import pytest

def test_assign_task_to_non_member(as_user, user_ids):
    alice = as_user("alice")
    
    # Create project by alice
    proj_res = alice.post("/api/projects", json={"name": "Project A"})
    assert proj_res.status_code == 201, proj_res.text
    pid = proj_res.json()["id"]
    
    # Create task
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    initial_assignee = task_res.json().get("assignee_id")
    
    # Pick a user who is not a project member (e.g., bob if bob is not added, or find one not in members)
    # Get all users to find one not in the project
    users_res = alice.get("/api/users")
    assert users_res.status_code == 200, users_res.text
    all_users = users_res.json()
    
    non_member_id = None
    for u in all_users:
        if u["username"] != "alice":
            non_member_id = u["id"]
            break
            
    assert non_member_id is not None
    
    # Try to patch task with non-member assignee
    patch_res = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": non_member_id})
    assert patch_res.status_code == 422, patch_res.text
    
    # Verify assignee remains unchanged
    get_task_res = alice.get(f"/api/tasks/{tid}")
    assert get_task_res.status_code == 200, get_task_res.text
    assert get_task_res.json()["assignee_id"] == initial_assignee, get_task_res.text


def test_assign_task_to_non_existent_user(as_user):
    alice = as_user("alice")
    
    # Create project by alice
    proj_res = alice.post("/api/projects", json={"name": "Project B"})
    assert proj_res.status_code == 201, proj_res.text
    pid = proj_res.json()["id"]
    
    # Create task
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Try to patch task with non-existent assignee ID
    patch_res = alice.patch(f"/api/tasks/{tid}", json={"assignee_id": 99999})
    assert patch_res.status_code == 422, patch_res.text
