import pytest


def test_tc1_create_task_boundary_title_lengths_and_default_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 1 character title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert task1["title"] == "a"
    assert task1["priority"] == 3

    # 100 characters title
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title})
    assert r2.status_code == 201, r2.text
    task2 = r2.json()
    assert task2["title"] == long_title
    assert task2["priority"] == 3


def test_tc2_create_task_invalid_title_empty_or_101_chars_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Empty title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text

    # 101 characters title
    too_long_title = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long_title})
    assert r2.status_code == 422, r2.text


def test_tc3_create_and_update_task_priority_boundaries_1_and_5(as_user, new_project):
    alice = as_user(
        "alice"
    )
    pid = new_project(owner="alice")

    # Create with priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1", "priority": 1})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    tid = task1["id"]
    assert task1["priority"] == 1

    # Update priority to 5
    r2 = alice.patch(f"/api/tasks/{tid}", json={"priority": 5})
    assert r2.status_code == 200, r2.text
    assert r2.json()["priority"] == 5


def test_tc4_update_task_invalid_priority_values_0_and_6_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r1.status_code == 201, r1.text
    tid = r1.json()["id"]

    # Priority 0
    r2 = alice.patch(f"/api/tasks/{tid}", json={"priority": 0})
    assert r2.status_code == 422, r2.text

    # Priority 6
    r3 = alice.patch(f"/api/tasks/{tid}", json={"priority": 6})
    assert r3.status_code == 422, r3.text
