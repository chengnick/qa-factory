import pytest

def test_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task (status defaults to todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
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


def test_tc2_forbidden_transitions_from_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task and transition to done
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Done Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    
    # 1. done -> todo (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # 2. done -> in_progress (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    
    # 3. done -> done (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    
    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_tc3_other_unlisted_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task (status todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # 1. todo -> done (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    
    # 2. todo -> todo (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Move to in_progress
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    
    # 3. in_progress -> in_progress (409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text


def test_tc4_invalid_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
