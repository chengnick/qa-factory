import pytest

def test_tc1_create_task_title_lengths(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 1-character title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["title"] == "a"
    
    # 100-character title
    title_100 = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100})
    assert r2.status_code == 201, r2.text
    assert r2.json()["title"] == title_100

def test_tc2_create_task_invalid_title_lengths(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Empty title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # 101-character title
    title_101 = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r2.status_code == 422, r2.text

def test_tc3_create_task_priorities(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Default priority
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Default"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["priority"] == 3
    
    # Min priority (1)
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P1", "priority": 1})
    assert r2.status_code == 201, r2.text
    assert r2.json()["priority"] == 1
    
    # Max priority (5)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P5", "priority": 5})
    assert r3.status_code == 201, r3.text
    assert r3.json()["priority"] == 5

def test_tc4_task_priority_boundaries_and_patch(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0 returns 422
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P0", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6 returns 422
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P6", "priority": 6})
    assert r2.status_code == 422, r2.text
    
    # Create a valid task for patching tests
    r_valid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Task"})
    assert r_valid.status_code == 201, r_valid.text
    tid = r_valid.json()["id"]
    
    # Patch with invalid priority 0 returns 422
    r3 = alice.patch(f"/api/tasks/{tid}", json={"priority": 0})
    assert r3.status_code == 422, r3.text
    
    # Patch with invalid priority 6 returns 422
    r4 = alice.patch(f"/api/tasks/{tid}", json={"priority": 6})
    assert r4.status_code == 422, r4.text
