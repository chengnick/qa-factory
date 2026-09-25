import pytest
import httpx

def test_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task
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
    
    # done -> to do (Wait, can done go back to todo? Let's check REQ-005: "todo to in_progress, in_progress to done, in_progress to todo". TC-1 steps show: in_progress to todo.)
    # Ah, let's look at TC-1 steps in the JSON carefully:
    # 1. POST /api/projects
    # 2. POST /api/projects/{pid}/tasks
    # 3. POST /api/tasks/{tid}/transition with {"to": "in_progress"}
    # 4. POST /api/tasks/{tid}/transition with {"to": "done"}
    # 5. POST /api/tasks/{tid}/transition with {"to": "todo"}
    # Wait, step 5 from done to todo? Let's verify what TC-1 actually does in the prompt steps.
    # Actually, let's follow the exact steps listed in TC-1:
    # Let's write a fresh task for the last step if done->todo fails (since done is terminal in TC-2).
    # Wait, let's re-read TC-1 steps:
    # 1. POST /api/projects
    # 2. POST /api/projects/{pid}/tasks
    # 3. POST ... to in_progress
    # 4. POST ... to done
    # 5. POST ... to todo (Wait, if 4 is done, 5 to todo would fail if done is terminal. Let's check if step 5 in TC-1 is in_progress to todo instead).
    # Let's test the transitions according to the requirement text: "todo to in_progress, in_progress to done, in_progress to todo"
    # So: todo -> in_progress -> todo -> in_progress -> done.

def test_tc1_valid_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    
    # in_progress -> todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"
    
    # todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    # in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

def test_tc2_done_is_terminal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]
    
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    
    # Attempt transition from done to todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status remains done
    r = alice.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

def test_tc3_invalid_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]
    
    # todo -> done (unlisted, should be 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"
    
    # self-transition: todo -> todo (should be 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # transition to in_progress
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    
    # self-transition: in_progress -> in_progress (should be 409)
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "in_progress"

def test_tc4_invalid_status_parameter(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
