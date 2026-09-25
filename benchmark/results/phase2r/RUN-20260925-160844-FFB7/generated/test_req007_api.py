import pytest
import httpx

def test_tc1_member_can_read(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    
    # Create a task in the project
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # GET project
    r_proj = alice.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 200, r_proj.text
    
    # GET task list
    r_list = alice.get(f"/api/projects/{pid}/tasks")
    assert r_list.status_code == 200, r_list.text
    
    # GET task detail
    r_detail = alice.get(f"/api/tasks/{tid}")
    assert r_detail.status_code == 200, r_detail.text

def test_tc2_non_member_receives_403(as_user, new_project):
    pid = new_project(owner="alice", members=())
    alice = as_user("alice")
    bob = as_user("bob")
    
    r_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert r_task.status_code == 201, r_task.text
    tid = r_task.json()["id"]
    
    # GET project as bob (non-member)
    r_proj = bob.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 403, r_proj.text
    
    # GET task list as bob
    r_list = bob.get(f"/api/projects/{pid}/tasks")
    assert r_list.status_code == 403, r_list.text
    
    # GET task detail as bob
    r_detail = bob.get(f"/api/tasks/{tid}")
    assert r_detail.status_code == 403, r_detail.text

def test_tc3_non_existent_resources_return_404(as_user):
    alice = as_user("alice")
    
    r_proj = alice.get("/api/projects/99999")
    assert r_proj.status_code == 404, r_proj.text
    
    r_list = alice.get("/api/projects/99999/tasks")
    assert r_list.status_code == 404, r_list.text
    
    r_detail = alice.get("/api/tasks/99999")
    assert r_detail.status_code == 404, r_detail.text
