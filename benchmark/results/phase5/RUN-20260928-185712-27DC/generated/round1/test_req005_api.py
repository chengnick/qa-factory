import pytest


def test_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task (starts as 'todo')
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"

    # TC-1: todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # TC-1: in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Reset for in_progress -> todo transition: create a new task and move to in_progress
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # TC-1: in_progress -> todo
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_transitions_from_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task, move it to in_progress, then to done
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Done Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # TC-2: done -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # TC-2: done -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text

    # TC-2: done -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_forbidden_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # TC-3: todo -> done (forbidden)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # TC-3: todo -> todo (same status)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Move to in_progress to test in_progress -> in_progress
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})

    # TC-3: in_progress -> in_progress (same status)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_invalid_status_parameter(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # TC-4: Invalid status parameter
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
