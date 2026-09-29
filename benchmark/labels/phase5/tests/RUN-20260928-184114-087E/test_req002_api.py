import pytest

def test_tc1_task_boundaries_and_defaults(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 1. title length 1, no priority (should default to 3)
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert task1["title"] == "a"
    assert task1["priority"] == 3

    # 2. title length 100, priority 1
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title, "priority": 1})
    assert r2.status_code in (200, 201), r2.text
    task2 = r2.json()
    assert task2["title"] == long_title
    assert task2["priority"] == 1

    # 3. title length 50, priority 5
    mid_title = "a" * 50
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": mid_title, "priority": 5})
    assert r3.status_code in (200, 201), r3.text
    task3 = r3.json()
    assert task3["title"] == mid_title
    assert task3["priority"] == 5


def test_tc2_task_title_invalid(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 1. title length 101 (>100)
    too_long = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long})
    assert r1.status_code == 422, r1.text

    # 2. title empty string
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text


def test_tc3_task_priority_out_of_range(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 1. priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "valid title", "priority": 0})
    assert r1.status_code == 422, r1.text

    # 2. priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "valid title", "priority": 6})
    assert r2.status_code == 422, r2.text
