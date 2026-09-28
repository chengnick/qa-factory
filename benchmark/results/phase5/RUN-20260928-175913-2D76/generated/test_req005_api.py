import pytest
import httpx

def test_req005_tc1_valid_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task (defaults to todo)
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]
    assert task["status"] == "todo"

    # 1. todo -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # 2. in_progress -> done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Setup another task for in_progress -> todo transition
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]
    
    r = client.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # 3. in_progress -> todo
    r = client.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_req005_tc2_done_forbidden_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # Move to in_progress then to done
    client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Try transitioning from done to todo
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Try transitioning from done to in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text

    # Try transitioning from done to done (self-transition)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text


def test_req005_tc3_other_unlisted_and_self_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Task in todo status
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r.status_code == 201, r.text
    tid_todo = r.json()["id"]

    # 1. todo -> done (unlisted)
    r = client.post(f"/api/tasks/{tid_todo}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # 2. todo -> todo (self-transition)
    r = client.post(f"/api/tasks/{tid_todo}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Task in in_progress status
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task In Progress"})
    assert r.status_code == 201, r.text
    tid_ip = r.json()["id"]
    client.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})

    # 3. in_progress -> in_progress (self-transition)
    r = client.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_req005_tc4_invalid_status_parameter(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
