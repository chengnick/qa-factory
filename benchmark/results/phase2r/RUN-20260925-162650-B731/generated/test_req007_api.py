import pytest

def test_tc1_member_can_read(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # GET /api/projects/{pid}
    r = alice.get(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    
    # POST task
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # GET task list
    r_list = alice.get(f"/api/projects/{pid}/tasks")
    assert r_list.status_code == 200, r_list.text
    
    # GET task detail
    r_detail = alice.get(f"/api/tasks/{tid}")
    assert r_detail.status_code == 200, r_detail.text


def test_tc2_non_member_forbidden(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # Non-member bob tries to read project, task list, task detail
    r1 = bob.get(f"/api/projects/{pid}")
    assert r1.status_code == 403, r1.text
    
    r2 = bob.get(f"/api/projects/{pid}/tasks")
    assert r2.status_code == 403, r2.text
    
    r3 = bob.get(f"/api/tasks/{tid}")
    assert r3.status_code == 403, r3.text


def test_tc3_not_found(as_user):
    alice = as_user("alice")
    
    r1 = alice.get("/api/projects/99999")
    assert r1.status_code == 404, r1.text
    
    r2 = alice.get("/api/projects/99999/tasks")
    assert r2.status_code == 404, r2.text
    
    r3 = alice.get("/api/tasks/99999")
    assert r3.status_code == 404, r3.text
