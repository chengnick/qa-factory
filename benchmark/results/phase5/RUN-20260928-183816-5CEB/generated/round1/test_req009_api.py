import pytest

def test_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Fix Login Bug"

def test_tc2_literal_percent_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100% complete"})
    assert r.status_code == 201, r.text
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "1000 complete"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=100%")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "100% complete"

def test_tc3_literal_underscore_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "user_name"})
    assert r.status_code == 201, r.text
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "userXname"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=user_name")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "user_name"

def test_tc4_search_status_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Test 1"})
    assert r1.status_code == 201, r1.text
    tid1 = r1.json()["id"]
    
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Test 2"})
    assert r2.status_code == 201, r2.text
    
    r = alice.post(f"/api/tasks/{tid1}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=Alpha&status=in_progress&limit=10&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["id"] == tid1
    assert data["items"][0]["status"] == "in_progress"
