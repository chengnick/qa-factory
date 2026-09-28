import pytest

def test_tc1_title_boundary_validation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Length 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A"})
    assert r1.status_code in (200, 201), r1.text

    # Length 100
    long_title_100 = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title_100})
    assert r2.status_code in (200, 201), r2.text

def test_tc2_title_violation_validation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Length 101
    long_title_101 = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title_101})
    assert r1.status_code == 422, r1.text

    # Empty string
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_default_and_boundary(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # No priority (default should be 3)
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Default"})
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["priority"] == 3, r1.text

    # Priority 1
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P1", "priority": 1})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["priority"] == 1, r2.text

    # Priority 5
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P5", "priority": 5})
    assert r3.status_code in (200, 201), r3.text
    assert r3.json()["priority"] == 5, r3.text

def test_tc4_priority_violation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P0", "priority": 0})
    assert r1.status_code == 422, r1.text

    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P6", "priority": 6})
    assert r2.status_code == 422, r2.text
