import pytest
import httpx

def test_req005_tc1_valid_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Task 1: todo -> in_progress -> done
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Task 2: todo -> in_progress -> todo
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_req005_tc2_done_state_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # transition to in_progress then done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Attempting to transition from done should return 409
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"


def test_req005_tc3_unlisted_and_self_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Task Todo: try todo -> done (invalid unlisted)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"

    # Self-transition on todo -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"

    # Task InProgress: try in_progress -> in_progress (self-transition)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task InProgress"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid2}").json()["status"] == "in_progress"


def test_req005_tc4_illegal_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
