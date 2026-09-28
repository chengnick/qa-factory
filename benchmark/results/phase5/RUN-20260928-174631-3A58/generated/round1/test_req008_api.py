import pytest

def test_tc1_owner_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by owner"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Delete task
    r_del = alice.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 204, r_del.text


def test_tc2_creator_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=("bob",))
    
    # Create task by bob (who is not the owner)
    r_task = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by creator bob"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Delete task by bob
    r_del = bob.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 204, r_del.text


def test_tc3_other_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=("bob",))
    
    # Create task by alice
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Bob attempts to delete alice's task
    r_del = bob.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 403, r_del.text
    
    # Verify task remains intact
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["id"] == tid


def test_tc4_non_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    carol = as_user("carol")
    pid = new_project(owner="alice")
    
    # Create task by alice
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Carol (non-member) attempts to delete the task
    r_del = carol.delete(f"/api/tasks/{tid}")
    assert r_del.status_code == 403, r_del.text
