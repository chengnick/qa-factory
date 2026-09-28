import pytest

def test_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task (starts in 'todo')
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]
    assert task["status"] == "todo"

    # 1. todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # 2. in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Setup another task to test in_progress -> todo
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # 3. in_progress -> todo
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc2_forbidden_transitions_from_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # Move task to done via in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Attempt done -> todo (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"

    # Attempt done -> in_progress (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_tc3_forbidden_unlisted_and_self_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"

    # 1. todo -> done (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # 2. todo -> todo (self-transition, 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Move to in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # 3. in_progress -> in_progress (self-transition, 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text

    # Move to done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text

    # 4. done -> done (self-transition, 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text


def test_tc4_invalid_state_parameter(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid Status"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
