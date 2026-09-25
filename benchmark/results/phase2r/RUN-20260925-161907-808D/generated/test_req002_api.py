import pytest

def test_tc1_title_boundaries_and_success(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 1 character title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code == 201, r1.text
    task_id = r1.json()["id"]
    
    # 100 character title
    title_100 = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100})
    assert r2.status_code == 201, r2.text
    
    # Update task title to 100 characters
    r3 = alice.patch(f"/api/tasks/{task_id}", json={"title": title_100})
    assert r3.status_code == 200, r3.text
    assert r3.json()["title"] == title_100

def test_tc2_title_invalid_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 101 character title
    title_101 = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r1.status_code == 422, r1.text
    
    # Empty string title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r2.status_code == 422, r2.text

def test_tc3_priority_boundaries_and_default(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Default priority (should be 3)
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Default Priority"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["priority"] == 3
    
    # Priority 1
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Priority 1", "priority": 1})
    assert r2.status_code == 201, r2.text
    assert r2.json()["priority"] == 1
    
    # Priority 5
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Priority 5", "priority": 5})
    assert r3.status_code == 201, r3.text
    assert r3.json()["priority"] == 5

def test_tc4_priority_out_of_bounds(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Priority 0", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Priority 6", "priority": 6})
    assert r2.status_code == 422, r2.text
