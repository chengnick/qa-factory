import pytest


def test_tc1_task_creation_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 1. 1 char title, priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a", "priority": 1})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert task1["title"] == "a"
    assert task1["priority"] == 1

    # 2. 100 chars title, priority 5
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title, "priority": 5})
    assert r2.status_code == 201, r2.text
    task2 = r2.json()
    assert task2["title"] == long_title
    assert task2["priority"] == 5

    # 3. valid title without priority (default 3)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "default priority task"})
    assert r3.status_code == 201, r3.text
    task3 = r3.json()
    assert task3["title"] == "default priority task"
    assert task3["priority"] == 3


def test_tc2_task_update_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r_init = alice.post(f"/api/projects/{pid}/tasks", json={"title": "initial title"})
    assert r_init.status_code == 201, r_init.text
    tid = r_init.json()["id"]

    long_title = "b" * 100
    r_update = alice.patch(f"/api/tasks/{tid}", json={"title": long_title, "priority": 5})
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["title"] == long_title
    assert updated["priority"] == 5


def test_tc3_task_title_invalid_length(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Empty title
    r_empty = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r_empty.status_code == 422, r_empty.text

    # Too long title (101 chars)
    too_long = "a" * 101
    r_long = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long})
    assert r_long.status_code == 422, r_long.text


def test_tc4_task_priority_invalid_range(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 0
    r_low = alice.post(f"/api/projects/{pid}/tasks", json={"title": "task", "priority": 0})
    assert r_low.status_code == 422, r_low.text

    # Priority 6
    r_high = alice.post(f"/api/projects/{pid}/tasks", json={"title": "task", "priority": 6})
    assert r_high.status_code == 422, r_high.text
