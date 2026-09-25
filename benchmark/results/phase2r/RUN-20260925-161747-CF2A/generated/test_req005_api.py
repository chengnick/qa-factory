import pytest


def test_tc1_allowed_task_status_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create task 1 (starts in 'todo')
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
    task = res.json()
    tid = task["id"]
    assert task["status"] == "todo"

    # todo -> in_progress
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_progress"

    # in_progress -> done
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"

    # Create task 2
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert res.status_code == 201, res.text
    task2 = res.json()
    tid2 = task2["id"]

    # todo -> in_progress
    res = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_progress"

    # in_progress -> todo
    res = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "todo"


def test_tc2_done_terminal_state(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
tid = res.json()["id"]

    # todo -> in_progress
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text

    # in_progress -> done
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"

    # done -> todo (should fail with 409)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert res.status_code == 409, res.text

    # done -> in_progress (should fail with 409)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 409, res.text

    # Verify status remains 'done'
    res = alice.get(f"/api/tasks/{tid}")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"


def test_tc3_unlisted_and_same_state_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
tid = res.json()["id"]

    # todo -> done (unlisted, should return 409)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 409, res.text

    # todo -> todo (same-state, should return 409)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert res.status_code == 409, res.text

    # transition to in_progress (valid)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text

    # in_progress -> in_progress (same-state, should return 409)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 409, res.text


def test_tc4_invalid_status_returns_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
tid = res.json()["id"]

    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert res.status_code == 422, res.text
