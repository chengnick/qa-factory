import pytest


def test_tc1_allowed_state_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")

    # Task 1: todo -> in_progress -> done
    r1 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r1.status_code == 201, r1.text
    tid = r1.json()["id"]

    r_trans1 = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r_trans1.status_code == 200, r_trans1.text
    assert r_trans1.json()["status"] == "in_progress"

    r_trans2 = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r_trans2.status_code == 200, r_trans2.text
    assert r_trans2.json()["status"] == "done"

    # Task 2: todo -> in_progress -> todo
    r2 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r2.status_code == 201, r2.text
    tid2 = r2.json()["id"]

    r_trans3 = client.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r_trans3.status_code == 200, r_trans3.text
    assert r_trans3.json()["status"] == "in_progress"

    r_trans4 = client.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r_trans4.status_code == 200, r_trans4.text
    assert r_trans4.json()["status"] == "todo"


def test_tc2_transitions_from_done_state(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")

    r1 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r1.status_code == 201, r1.text
    tid = r1.json()["id"]

    # Transition to in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # Transition to done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text

    # Attempt transition from done to todo (should fail with 409)
    r_fail = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r_fail.status_code == 409, r_fail.text

    # Verify status remains done
    r_get = client.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["status"] == "done"


def test_tc3_unlisted_and_self_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")

    r1 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r1.status_code == 201, r1.text
    tid = r1.json()["id"]

    # Unlisted transition: todo -> done (should fail with 409)
    r_fail1 = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r_fail1.status_code == 409, r_fail1.text

    # Self-transition: todo -> todo (should fail with 409)
    r_fail2 = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r_fail2.status_code == 409, r_fail2.text


def test_tc4_invalid_status_parameter(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")

    r1 = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid"})
    assert r1.status_code == 201, r1.text
    tid = r1.json()["id"]

    r_fail = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r_fail.status_code == 422, r_fail.text
