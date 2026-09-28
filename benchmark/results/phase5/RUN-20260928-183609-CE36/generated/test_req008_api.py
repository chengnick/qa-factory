import pytest

def test_tc1_project_owner_can_delete_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Delete the task as alice (project owner)
    del_res = alice.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_tc2_task_creator_can_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    # Add bob as a member
    mem_res = alice.post(f"/api/projects/{pid}/members", json={"user_id": user_ids["bob"]})
    assert mem_res.status_code == 201, mem_res.text
    
    # Create a task as bob
    task_res = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Bob Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Delete the task as bob (task creator)
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_tc3_other_project_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    # Add bob as a member
    mem_res = alice.post(f"/api/projects/{pid}/members", json={"user_id": user_ids["bob"]})
    assert mem_res.status_code == 201, mem_res.text
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Try to delete the task as bob (other project member)
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    # Verify task still exists
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid

def test_tc4_non_project_member_cannot_delete_task(as_user, new_project):
    alice = as_user("alice")
    carol = as_user("carol")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Try to delete the task as carol (non-project member)
    del_res = carol.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    # Verify task still exists
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid
