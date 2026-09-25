import pytest


def test_req005_tc1_valid_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task (status defaults to 'todo')
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    assert res.json()["status"] == "todo"

    # 1. todo -> in_progress
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_progress"

    # 2. in_progress -> done
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 200, res.text
    assert res.json()[
        "status"
    ] == "done"  # Note: next tests need in_progress, so we create a new task or transition back

    # Create another task for in_progress -> todo
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert res.status_code == 201, res.text
    tid2 = res.json()["id"]

    res = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text

    # 3. in_progress -> todo
    res = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "todo"


def test_req005_tc2_done_is_terminal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Terminal Task"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]

    # Move to in_progress then done
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Try done -> todo
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert res.status_code == 409, res.text
    # Verify status unchanged
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"

    # Try done -> in_progress
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 409, res.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"


def test_req005_tc3_unlisted_and_self_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    tid = res.json()["id"]

    # 1. todo -> done (unlisted)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 409, res.text

    # 2. todo -> todo (self-transition)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert res.status_code == 409, res.text

    # Move task to in_progress for further checks
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})

    # 3. in_progress -> in_progress (self-transition)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 409, res.text

    # Move task to done
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # 4. done -> done (self-transition)
    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 409, res.text


def test_req005_tc4_invalid_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    tid = res.json()["id"]

    res = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert res.status_code == 422, res.text
