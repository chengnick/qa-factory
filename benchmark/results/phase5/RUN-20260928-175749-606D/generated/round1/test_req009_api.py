import pytest

def test_req009_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r.status_code == 201, r.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1, data
    assert data["items"][0]["title"] == "Fix Login Bug", data

def test_req009_tc2_literal_wildcards(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100% complete_task"})
    assert r.status_code == 201, r.text
    
    # Test literal '%'
    r = alice.get(f"/api/projects/{pid}/tasks?q=%25")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1, data
    assert data["items"][0]["title"] == "100% complete_task", data
    
    # Test literal '_'
    r = alice.get(f"/api/projects/{pid}/tasks?q=_")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1, data
    assert data["items"][0]["title"] == "100% complete_task", data

def test_req009_tc3_simultaneous_search_status_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Task One"})
    assert r1.status_code == 201, r1.text
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Alpha Task Two"})
    assert r2.status_code == 201, r2.text
    
    r = alice.get(f"/api/projects/{pid}/tasks?q=Alpha&status=todo&limit=1&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2, data
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Alpha Task One", data
    assert data["limit"] == 1, data
    assert data["offset"] == 0, data
