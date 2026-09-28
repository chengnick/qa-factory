import pytest

def test_req009_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Fix Login Bug"

def test_req009_tc2_special_characters_literals(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100% complete_task"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=100%")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "100% complete_task"
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=_task")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "100% complete_task"

def test_req009_tc3_simultaneous_search_status_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Test"})
    assert r1.status_code == 201, r1.text
    t1_id = r1.json()["id"]
    
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Beta"})
    assert r2.status_code == 201, r2.text
    t2_id = r2.json()["id"]
    
    r = alice.post(f"/api/tasks/{t2_id}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=Alpha&status=in_progress&limit=10&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["id"] == t2_id
    assert data["items"][0]["title"] == "Alpha Beta"
    assert data["items"][0]["status"] == "in_progress"
