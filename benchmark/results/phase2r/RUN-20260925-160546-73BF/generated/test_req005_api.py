import pytest
import httpx

def test_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task (status is todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]
    assert task["status"] == "todo"
    
    # Transition todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    
    # Transition in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_tc2_backward_transition(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    # in_progress -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc3_forbidden_transition_from_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 3"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> in_progress -> done
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    
    # done -> todo (should fail with 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_tc4_forbidden_todo_to_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 4"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> done directly (should fail with 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    
    # Verify status remains todo
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc5_forbidden_self_state_transition(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 5"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> todo (should fail with 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status remains todo
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc6_invalid_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 6"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
