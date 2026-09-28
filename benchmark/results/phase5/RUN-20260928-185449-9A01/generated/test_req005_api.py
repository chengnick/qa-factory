import pytest
import httpx

def test_req005_tc1_allowed_status_transitions(as_user):
    client = as_user("alice")
    
    # Create project
    res = client.post("/api/projects", json={"name": "Proj 1"})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    
    # Create task
    res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    assert res.json()["status"] == "todo"
    
    # todo -> in_progress
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "in_progress"
    
    # in_progress -> done
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"
    
    # To allow testing done -> in_progress -> todo for the next transition test or direct check:
    # Wait, TC-1 specifies allowed: todo -> in_progress, in_progress -> done, in_progress -> todo.
    # Let's create another task to test in_progress -> todo transition specifically.
    res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1b"})
    assert res.status_code == 201, res.text
    tid_b = res.json()["id"]
    
    res = client.post(f"/api/tasks/{tid_b}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    
    res = client.post(f"/api/tasks/{tid_b}/transition", json={"to": "todo"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "todo"


def test_req005_tc2_transition_from_done_returns_409(as_user):
    client = as_user("alice")
    
    res = client.post("/api/projects", json={"name": "Proj 2"})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    
    res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    
    # todo -> in_progress
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 200, res.text
    
    # in_progress -> done
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"
    
    # done -> in_progress (should fail with 409 and status remains done)
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert res.status_code == 409, res.text
    
    # verify status unchanged
    res = client.get(f"/api/tasks/{tid}")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done"


def test_req005_tc3_forbidden_transitions(as_user):
    client = as_user("alice")
    
    res = client.post("/api/projects", json={"name": "Proj 3"})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    
    res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 3"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    assert res.json()["status"] == "todo"
    
    # todo -> done (forbidden -> 409)
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert res.status_code == 409, res.text
    
    # todo -> todo (same status transition -> 409)
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert res.status_code == 409, res.text


def test_req005_tc4_invalid_to_field_value_returns_422(as_user):
    client = as_user("alice")
    
    res = client.post("/api/projects", json={"name": "Proj 4"})
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    
    res = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 4"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    
    # invalid status -> 422
    res = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert res.status_code == 422, res.text
