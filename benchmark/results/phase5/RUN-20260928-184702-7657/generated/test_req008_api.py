import pytest

def test_owner_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create task
    res_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by owner"})
    assert res_task.status_code == 201, res_task.text
    tid = res_task.json()["id"]
    
    # Delete task
    res_del = alice.delete(f"/api/tasks/{tid}")
    assert res_del.status_code == 204, res_del.text


def test_creator_who_is_not_owner_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=("bob",))
    
    # Bob creates task
    res_task = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by bob"})
    assert res_task.status_code == 201, res_task.text
    tid = res_task.json()["id"]
    
    # Bob deletes task
    res_del = bob.delete(f"/api/tasks/{tid}")
    assert res_del.status_code == 204, res_del.text


def test_other_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=("bob",))
    
    # Alice creates task
    res_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert res_task.status_code == 201, res_task.text
    tid = res_task.json()["id"]
    
    # Bob attempts to delete task
    res_del = bob.delete(f"/api/tasks/{tid}")
    assert res_del.status_code == 403, res_del.text
    
    # Verify task still exists
    res_get = alice.get(f"/api/tasks/{tid}")
    assert res_get.status_code == 200, res_get.text


def test_non_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    carol = as_user("carol")
    pid = new_project(owner="alice", members=())
    
    # Alice creates task
    res_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert res_task.status_code == 201, res_task.text
    tid = res_task.json()["id"]
    
    # Carol (non-member) attempts to delete task
    res_del = carol.delete(f"/api/tasks/{tid}")
    assert res_del.status_code == 403, res_del.text
