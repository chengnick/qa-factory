import pytest

def test_req002_tc1_boundary_title_and_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Title length 1, priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A", "priority": 1})
    assert r1.status_code in (200, 201), r1.text
    task1 = r1.json()
    assert task1["title"] == "A"
    assert task1["priority"] == 1

    # Title length 100, priority 5
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title, "priority": 5})
    assert r2.status_code in (200, 201), r2.text
    task2 = r2.json()
    assert task2["title"] == long_title
    assert task2["priority"] == 5

    # Default priority (3)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Default Priority Task"})
    assert r3.status_code in (200, 201), r3.text
    task3 = r3.json()
    assert task3["title"] == "Default Priority Task"
    assert task3["priority"] == 3

def test_req002_tc2_invalid_title_and_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Empty title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "", "priority": 3})
    assert r1.status_code == 422, r1.text

    # Title too long (101 chars)
    too_long_title = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long_title, "priority": 3})
    assert r2.status_code == 422, r2.text

    # Priority below range (0)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r3.status_code == 422, r3.text

    # Priority above range (6)
    r4 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r4.status_code == 422, r4.text
