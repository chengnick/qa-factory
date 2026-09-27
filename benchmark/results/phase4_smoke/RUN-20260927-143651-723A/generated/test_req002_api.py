import pytest
import httpx

def test_tc1_create_task_boundary_title_lengths(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title with length 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code in (200, 201), r1.text
    
    # Title with length 100
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title})
    assert r2.status_code in (200, 201), r2.text

def test_tc2_create_task_invalid_title_lengths_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Blank title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # Title with length 101
    too_long_title = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long_title})
    assert r2.status_code == 422, r2.text

def test_tc3_create_task_boundary_priority_values(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1", "priority": 1})
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["priority"] == 1
    
    # Priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2", "priority": 5})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["priority"] == 5

def test_tc4_create_task_invalid_priority_values_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2", "priority": 6})
    assert r2.status_code == 422, r2.text

def test_tc5_update_task_invalid_boundaries_422(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    create_r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title"})
    assert create_r.status_code in (200, 201), create_r.text
    tid = create_r.json()["id"]
    
    # Update title to blank
    r1 = alice.patch(f"/api/tasks/{tid}", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # Update priority to 0
    r2 = alice.patch(f"/api/tasks/{tid}", json={"priority": 0})
    assert r2.status_code == 422, r2.text
