import pytest

def test_req007_tc1_member_can_read_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["id"] == tid
    assert get_res.json()["title"] == "Test Task"

def test_req007_tc2_non_member_forbidden(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    get_res = bob.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 403, get_res.text

def test_req007_tc3_non_existent_task_not_found(as_user):
    alice = as_user("alice")
    get_res = alice.get("/api/tasks/99999")
    assert get_res.status_code == 404, get_res.text
