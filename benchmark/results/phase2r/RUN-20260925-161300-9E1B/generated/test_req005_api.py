import pytest

def test_req005_tc1_valid_state_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task (status starts as todo)
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

    # Create another task to test in_progress -> todo
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # 3. in_progress -> todo
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_req005_tc2_transitions_from_done_state(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task and transition to done
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Done Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Try to transition done -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Try to transition done -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text

    # Try to transition done -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_req005_tc3_other_unlisted_and_self_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create task (todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    tid = r.json()["id"]

    # todo -> done (unlisted)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # todo -> todo (self-transition)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Move to in_progress
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})

    # in_progress -> in_progress (self-transition)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_req005_tc4_invalid_status_parameter(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
