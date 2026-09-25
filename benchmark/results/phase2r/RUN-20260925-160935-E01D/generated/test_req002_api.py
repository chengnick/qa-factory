import pytest


def test_tc1_title_boundary_100_and_priority_range(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Title of exactly 100 characters with priority 1
    title_100 = "a" * 100
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100, "priority": 1})
    assert r1.status_code == 201, r1.text
    data1 = r1.json()
    assert data1["title"] == title_100
    assert data1["priority"] == 1

    # Title of 1 character with priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A", "priority": 5})
    assert r2.status_code == 201, r2.text
    data2 = r2.json()
    assert data2["title"] == "A"
    assert data2["priority"] == 5


def test_tc2_title_invalid_length_or_empty(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Title of 101 characters
    title_101 = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101, "priority": 3})
    assert r1.status_code == 422, r1.text

    # Empty title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "", "priority": 3})
    assert r2.status_code == 422, r2.text

    # Whitespace-only title
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "   ", "priority": 3})
    assert r3.status_code == 422, r3.text


def test_tc3_priority_out_of_bounds(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r1.status_code == 422, r1.text

    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r2.status_code == 422, r2.text


def test_tc4_default_priority_is_3(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Post without priority
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Default Priority Task"})
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["priority"] == 3
