import pytest

def test_req009_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Fix Login Bug"

def test_req009_tc2_literal_special_characters(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100% complete_task"})
    assert r.status_code == 201, r.text
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100A complete_taskX"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=100%")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "100% complete_task"
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=_complete")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "100% complete_task"

def test_req009_tc3_search_with_status_and_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Login feature A"})
    assert r.status_code == 201, r.text
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Login feature B"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=Login&status=todo&limit=1&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 1, data
    assert data["offset"] == 0, data
    assert data["total"] == 2, data
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Login feature A"
