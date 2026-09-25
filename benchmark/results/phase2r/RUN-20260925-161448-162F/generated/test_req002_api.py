import pytest

def test_tc1_title_boundaries_and_required(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Length 1
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A"})
    assert r.status_code == 201, r.text

    # Length 100
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A" * 100})
    assert r.status_code == 201, r.text

    # Empty string
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r.status_code == 422, r.text

    # Whitespace only
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "   "})
    assert r.status_code == 422, r.text

def test_tc2_title_too_long(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Length 101
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A" * 101})
    assert r.status_code == 422, r.text

def test_tc3_priority_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 1
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1", "priority": 1})
    assert r.status_code == 201, r.text
    assert r.json()["priority"] == 1

    # Priority 5
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 5", "priority": 5})
    assert r.status_code == 201, r.text
    assert r.json()["priority"] == 5

def test_tc4_priority_out_of_range(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 0
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 0", "priority": 0})
    assert r.status_code == 422, r.text

    # Priority 6
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 6", "priority": 6})
    assert r.status_code == 422, r.text
