import pytest
import httpx

def test_owner_deletes_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob",))
    alice = as_user("alice")
    
    # Create a task as alice (owner)
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Owner"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Owner deletes task
    del_res = alice.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_creator_deletes_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob",))
    alice = as_user("alice")
    bob = as_user("bob")
    
    # Create a task as bob (member, not owner)
    task_res = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Bob"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Task creator (bob) deletes task
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_other_member_attempts_to_delete_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob", "carol"))
    alice = as_user("alice")
    carol = as_user("carol")
    
    # Create a task as alice (owner)
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Carol (member, not owner/creator) attempts to delete task
    del_res = carol.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    # Verify task still exists
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text

def test_non_member_attempts_to_delete_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob",))
    alice = as_user("alice")
    dave = as_user("dave")
    
    # Create a task as alice (owner)
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Dave (non-member) attempts to delete task
    del_res = dave.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    # Verify task still exists
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
