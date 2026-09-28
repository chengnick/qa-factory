import pytest

def test_tc1_project_owner_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Alice"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Delete the task as alice (project owner)
    r_del = alice.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 204, r_del.text


def test_tc2_task_creator_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    
    pid = new_project(owner="alice", members=("bob",))
    
    # Create a task as bob (member, not project owner)
    r_task = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Bob"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Delete the task as bob (task creator)
    r_del = bob.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 204, r_del.text


def test_tc3_other_project_member_attempts_to_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    
    pid = new_project(owner="alice", members=("bob",))
    
    # Create a task as alice
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Alice"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Attempt to delete the task as bob (other project member)
    r_del = bob.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 403, r_del.text
    
    # Verify task still exists
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["id"] == tid


def test_tc4_non_project_member_attempts_to_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    carol = as_user("carol")
    
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Alice"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Attempt to delete the task as carol (non-project member)
    r_del = carol.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 403, r_del.text
