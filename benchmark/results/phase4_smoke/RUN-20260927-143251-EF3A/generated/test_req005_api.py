import pytest

def test_valid_state_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task (defaults to todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"

    # todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Create another task for in_progress -> todo transition
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # in_progress -> todo
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_transitions_from_done_state(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # Transition to done first
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # done -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"

    # done -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"

    # done -> done (self transition)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "done"


def test_unlisted_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # todo -> done (unlisted)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"

    # todo -> todo (self-transition)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"

    # Setup in_progress task for self-transition test
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task In Progress"})
    tid_ip = r.json()["id"]
    alice.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})

    # in_progress -> in_progress (self-transition)
    r = alice.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid_ip}").json()["status"] == "in_progress"


def test_invalid_status_parameter(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
