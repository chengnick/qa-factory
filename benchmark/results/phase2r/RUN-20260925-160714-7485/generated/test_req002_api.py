import pytest
import httpx

def test_tc1_title_boundary_and_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title of exactly 100 characters, priority 1
    title_100 = "a" * 100
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100, "priority": 1})
    assert r1.status_code in (200, 201), r1.text
    
    # Priority 5 with default valid title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 5})
    assert r2.status_code in (200, 201), r2.text

def test_tc2_title_too_long_or_empty(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title of 101 characters -> 422
    title_101 = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r1.status_code == 422, r1.text
    
    # Empty title "" -> 422
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_invalid_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0 -> 422
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6 -> 422
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r2.status_code == 422, r2.text
