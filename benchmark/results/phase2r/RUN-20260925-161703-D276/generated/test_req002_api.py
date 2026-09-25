import pytest

def test_tc1_title_boundaries_and_default_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert task1["title"] == "a"
    assert task1["priority"] == 3

    # Title length 100
    title_100 = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100})
    assert r2.status_code == 201, r2.text
    task2 = r2.json()
    assert task2["title"] == title_100

def test_tc2_invalid_title_length_or_empty(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title length 101
    title_101 = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r1.status_code == 422, r1.text

    # Title empty string
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P1", "priority": 1})
    assert r1.status_code == 201, r1.text
    assert r1.json()["priority"] == 1

    # Priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P5", "priority": 5})
    assert r2.status_code == 201, r2.text
    assert r2.json()["priority"] == 5

def test_tc4_priority_out_of_bounds(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P0", "priority": 0})
    assert r1.status_code == 422, r1.text

    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P6", "priority": 6})
    assert r2.status_code == 422, r2.text
