import pytest


def test_tc1_task_title_and_priority_boundary(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 100 character title with priority 1
    title_100 = "a" * 100
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100, "priority": 1})
    assert r1.status_code == 201, r1.text
    task1 = r1.json()
    assert len(task1["title"]) == 100
    assert task1["priority"] == 1

    # priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task with priority 5", "priority": 5})
    assert r2.status_code == 201, r2.text
    task2 = r2.json()
    assert task2["priority"] == 5


def test_tc2_update_task_title_length_and_default_priority(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a default task
    r_create = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Original Title"})
    assert r_create.status_code == 201, r_create.text
    tid = r_create.json()["id"]

    # PATCH with 100 character title and no priority provided
    title_100 = "b" * 100
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"title": title_100})
    assert r_patch.status_code == 200, r_patch.text
    updated_task = r_patch.json()
    assert len(updated_task["title"]) == 100
    assert updated_task["priority"] == 3


def test_tc3_task_title_too_long_or_empty(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # 101 characters title
    title_101 = "c" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r1.status_code == 422, r1.text

    # Empty title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text


def test_tc4_task_priority_out_of_range_on_create(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r1.status_code == 422, r1.text

    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r2.status_code == 422, r2.text


def test_tc5_task_priority_out_of_range_on_update(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r_create = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title"})
    assert r_create.status_code == 201, r_create.text
    tid = r_create.json()["id"]

    # Priority 0 update
    r1 = alice.patch(f"/api/tasks/{tid}", json={"priority": 0})
    assert r1.status_code == 422, r1.text

    # Priority 6 update
    r2 = alice.patch(f"/api/tasks/{tid}", json={"priority": 6})
    assert r2.status_code == 422, r2.text
