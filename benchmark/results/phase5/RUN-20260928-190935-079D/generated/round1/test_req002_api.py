import pytest

def test_tc1_title_boundaries_and_default_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title of length 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert task1["title"] == "a"
    assert task1["priority"] == 3
    
    # Title of length 100
    long_title = "A" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title})
    assert r2.status_code == 201, r2.text
    task2 = r2.json()
    assert task2["title"] == long_title
    assert task2["priority"] == 3

def test_tc2_title_invalid_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Empty title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # Title exceeding 100 characters
    too_long_title = "A" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long_title})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_valid_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1", "priority": 1})
    assert r1.status_code == 201, r1.text
    assert r1.json()["priority"] == 1
    
    # Priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 5", "priority": 5})
    assert r2.status_code == 201, r2.text
    assert r2.json()["priority"] == 5

def test_tc4_priority_invalid_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 0", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 6", "priority": 6})
    assert r2.status_code == 422, r2.text
