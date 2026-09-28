import pytest
import httpx

def test_tc1_create_task_boundary_titles(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 1 character title, no priority
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "A"})
    assert r1.status_code in (200, 201), r1.text
    
    # 100 characters title (max boundary)
    long_title = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title})
    assert r2.status_code in (200, 201), r2.text
    data = r2.json()
    assert data["title"] == long_title

def test_tc2_create_update_invalid_titles(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Empty title create
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # Exceeding 100 characters title create
    too_long_title = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long_title})
    assert r2.status_code == 422, r2.text
    
    # Create a valid task first
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title"})
    assert r3.status_code in (200, 201), r3.text
    tid = r3.json()["id"]
    
    # Patch with empty title
    r4 = alice.patch(f"/api/tasks/{tid}", json={"title": ""})
    assert r4.status_code == 422, r4.text

def test_tc3_create_task_priority_boundaries_and_default(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Default priority
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task default"})
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["priority"] == 3
    
    # Min priority 1
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task min", "priority": 1})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["priority"] == 1
    
    # Max priority 5
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task max", "priority": 5})
    assert r3.status_code in (200, 201), r3.text
    assert r3.json()["priority"] == 5

def test_tc4_create_patch_invalid_priorities(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0 on create
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6 on create
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task", "priority": 6})
    assert r2.status_code == 422, r2.text
    
    # Create valid task
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Task"})
    assert r3.status_code in (200, 201), r3.text
    tid = r3.json()["id"]
    
    # Patch with priority 0
    r4 = alice.patch(f"/api/tasks/{tid}", json={"priority": 0})
    assert r4.status_code == 422, r4.text
    
    # Patch with priority 6
    r5 = alice.patch(f"/api/tasks/{tid}", json={"priority": 6})
    assert r5.status_code == 422, r5.text
