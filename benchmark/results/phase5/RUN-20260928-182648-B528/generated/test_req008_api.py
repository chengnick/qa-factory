import pytest


def test_owner_deletes_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by owner"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = alice.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text


def test_task_creator_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    
    pid = new_project(owner="alice")
    
    member_res = alice.post(f"/api/projects/{pid}/members", json={"user_id": user_ids["bob"]})
    assert member_res.status_code == 201, member_res.text
    
    task_res = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by bob"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text


def test_member_not_owner_nor_creator_deletes_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    
    pid = new_project(owner="alice")
    
    member_res = alice.post(f"/api/projects/{pid}/members", json={"user_id": user_ids["bob"]})
    assert member_res.status_code == 201, member_res.text
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    check_res = alice.get(f"/api/tasks/{tid}")
    assert check_res.status_code == 200, check_res.text


def test_non_member_deletes_task(as_user, new_project):
    alice = as_user("alice")
    carol = as_user("carol")
    
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    del_res = carol.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
