import pytest

def test_req007_tc1_member_can_read(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task One"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    r_proj = alice.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 200, r_proj.text
    
    r_list = alice.get(f"/api/projects/{pid}/tasks")
    assert r_list.status_code == 200, r_list.text
    
    r_detail = alice.get(f"/api/tasks/{tid}")
    assert r_detail.status_code == 200, r_detail.text

def test_req007_tc2_non_member_forbidden(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")
    
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Beta"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    r_proj = bob.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 403, r_proj.text
    
    r_list = bob.get(f"/api/projects/{pid}/tasks")
    assert r_list.status_code == 403, r_list.text
    
    r_detail = bob.get(f"/api/tasks/{tid}")
    assert r_detail.status_code == 403, r_detail.text

def test_req007_tc3_non_existent_task(as_user):
    alice = as_user("alice")
    r = alice.get("/api/tasks/9999")
    assert r.status_code == 404, r.text
