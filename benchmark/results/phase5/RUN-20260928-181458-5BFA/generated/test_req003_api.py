import pytest

def test_req003_tc1_limit_offset_validation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # limit=0 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=0")
    assert r.status_code == 422, r.text
    
    # limit=101 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=101")
    assert r.status_code == 422, r.text
    
    # offset=-1 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?offset=-1")
    assert r.status_code == 422, r.text

def test_req003_tc2_default_limit_offset(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 20
    assert data["offset"] == 0

def test_req003_tc3_total_unaffected_by_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create 3 tasks
    for i in range(3):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})
        
    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["total"] == 3
    assert len(d1["items"]) == 1
    
    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=1")
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["total"] == 3
    assert len(d2["items"]) == 1
    assert d1["items"][0]["id"] != d2["items"][0]["id"]

def test_req003_tc4_paginated_iteration(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    created_ids = []
    for i in range(3):
        r = alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})
        created_ids.append(r.json()["id"])
        
    # Page 1
    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=0")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    items1 = d1["items"]
    assert len(items1) == 2
    
    # Page 2
    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=2")
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    items2 = d2["items"]
    assert len(items2) == 1
    
    all_fetched_ids = [item["id"] for item in items1 + items2]
    assert sorted(all_fetched_ids) == sorted(created_ids)

def test_req003_tc5_offset_gte_total_empty_items(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    
    r = alice.get(f"/api/projects/{pid}/tasks?offset=999")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"] == []
