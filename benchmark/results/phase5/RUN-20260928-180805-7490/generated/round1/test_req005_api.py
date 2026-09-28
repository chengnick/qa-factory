import pytest


def test_tc1_transition_todo_to_in_progress(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    task_res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    trans_res = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert trans_res.status_code == 200, trans_res.text
    assert trans_res.json()["status"] == "in_progress"


def test_tc2_transition_in_progress_to_done_and_todo(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    task_res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    # to in_progress
    r1 = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "in_progress"

    # to done
    r2 = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "done"


def test_tc3_transition_from_done_returns_409(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    task_res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 3"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    # todo -> in_progress -> done
    client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Try to transition from done to todo (or any other state)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Check state unchanged
    get_res = client.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["status"] == "done"


def test_tc4_forbidden_transitions_return_409(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    task_res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 4"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    # todo -> done (forbidden)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # todo -> todo (same state, forbidden)
    r2 = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r2.status_code == 409, r2.text


def test_tc5_transition_invalid_status_returns_422(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    task_res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 5"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]

    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
