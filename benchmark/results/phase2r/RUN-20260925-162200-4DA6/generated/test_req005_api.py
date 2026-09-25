import pytest
import httpx

def test_req005_tc1_allowed_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"
    
    # todo -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    
    # in_progress -> done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    
    # To allow in_progress -> todo for the next step, we need a new task or reset/transition logic if allowed.
    # Wait, the spec says: \u5141\u8a31\u5f9e in_progress \u6d41\u8f49\u81f3 todo. Let's create another task to test in_progress -> todo directly.
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1b"})
    assert r.status_code == 201, r.text
    tid_b = r.json()["id"]
    
    # todo -> in_progress
    r = client.post(f"/api/tasks/{tid_b}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    # in_progress -> todo
    r = client.post(f"/api/tasks/{tid_b}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_req005_tc2_terminal_state_restriction(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    # in_progress -> done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    
    # done -> todo (should fail with 409 and remain done)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status is still done
    r = client.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_req005_tc3_forbidden_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 3"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"
    
    # todo -> done (forbidden, should return 409)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    
    # todo -> todo (self-transition, should return 409)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Transition to in_progress first to test in_progress -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    # in_progress -> in_progress (self-transition, should return 409)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_req005_tc4_invalid_target_status(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice")
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 4"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # invalid status -> 422
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
