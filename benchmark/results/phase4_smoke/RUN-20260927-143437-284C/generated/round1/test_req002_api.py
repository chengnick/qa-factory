import pytest

def test_tc1_create_task_boundary_titles(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 1 char title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a"})
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["title"] == "a"
    
    # 100 chars title
    title_100 = "a" * 100
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["title"] == title_100

def test_tc2_create_task_invalid_titles(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Empty title
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": ""})
    assert r1.status_code == 422, r1.text
    
    # 101 chars title
    title_101 = "a" * 101
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101})
    assert r2.status_code == 422, r2.text

def test_tc3_create_task_boundary_priorities(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 1
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P1", "priority": 1})
    assert r1.status_code in (200, 201), r1.text
    assert r1.json()["priority"] == 1
    
    # Priority 5
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P5", "priority": 5})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["priority"] == 5
    
    # Default priority (omitted)
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Default"})
    assert r3.status_code in (200, 201), r3.text
    assert r3.json()["priority"] == 3

def test_tc4_create_task_invalid_priorities(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P0", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task P6", "priority": 6})
    assert r2.status_code == 422, r2.text
