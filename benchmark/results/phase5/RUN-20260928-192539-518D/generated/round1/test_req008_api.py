import pytest

def test_project_owner_deletes_task(as_user, new_project):
    pid = new_project(owner="alice")
    alice = as_user("alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Owner"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = alice.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text


def test_task_creator_deletes_task(as_user, new_project, user_ids):
    pid = new_project(owner="alice", members=("bob",))
    alice = as_user("alice")
    bob = as_user("bob")
    
    task_res = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by Bob"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text


def test_other_member_cannot_delete_task(as_user, new_project):
    pid = new_project(owner="alice", members=("bob",))
    alice = as_user("alice")
    bob = as_user("bob")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid


def test_non_member_cannot_delete_task(as_user, new_project):
    pid = new_project(owner="alice")
    alice = as_user("alice")
    carol = as_user("carol")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alice Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = carol.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
