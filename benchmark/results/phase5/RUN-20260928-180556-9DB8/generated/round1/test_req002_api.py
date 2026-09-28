import pytest
import httpx

def test_tc1_title_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length = 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    
    # Title length = 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 100})
    assert r2.status_code == 201, r2.text

def test_tc2_title_invalid(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length = 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 101})
    assert r1.status_code == 422, r1.text
    
    # Title is empty
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_boundaries_and_default(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority = 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P1", "priority": 1})
    assert r1.status_code == 201, r1.text
    assert r1.json()["priority"] == 1
    
    # Priority = 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P5", "priority": 5})
    assert r2.status_code == 201, r2.text
    assert r2.json()["priority"] == 5
    
    # Default priority (not provided)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Default"})
    assert r3.status_code == 201, r3.text
    assert r3.json()["priority"] == 3

def test_tc4_priority_out_of_range(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority = 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P0", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority = 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P6", "priority": 6})
    assert r2.status_code == 422, r2.text
