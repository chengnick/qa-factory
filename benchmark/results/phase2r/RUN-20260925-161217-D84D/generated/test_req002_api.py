import pytest

def test_tc1_title_length_100_and_priorities_1_and_5(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length 100, priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 100, "priority": 1})
    assert r1.status_code in (200, 201), r1.text
    
    # Valid title, priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 5})
    assert r2.status_code in (200, 201), r2.text

def test_tc2_title_length_101_and_empty_title_return_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 101})
    assert r1.status_code == 422, r1.text
    
    # Empty title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_boundaries_0_and_6_return_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task", "priority": 6})
    assert r2.status_code == 422, r2.text
