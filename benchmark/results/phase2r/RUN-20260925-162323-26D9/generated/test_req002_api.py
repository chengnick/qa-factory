import pytest

def test_tc1_title_boundary_and_priority_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # POST task with title length 100 and priority 1
    long_title = "a" * 100
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": long_title, "priority": 1})
    assert r1.status_code == 201, r1.text
    task = r1.json()
    tid = task["id"]
    assert len(task["title"]) == 100
    assert task["priority"] == 1
    
    # PATCH task with priority 5
    r2 = alice.patch(f"/api/tasks/{tid}", json={"priority": 5})
    assert r2.status_code == 200, r2.text
    assert r2.json()["priority"] == 5

def test_tc2_title_too_long_or_blank(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Title > 100 chars (101 'a's)
    too_long = "a" * 101
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": too_long, "priority": 3})
    assert r1.status_code == 422, r1.text
    assert r1.status_code < 500
    
    # Blank title
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "   ", "priority": 3})
    assert r2.status_code == 422, r2.text
    assert r2.status_code < 500

def test_tc3_priority_out_of_bounds(as_user, new_project):
    alice = as_user(
        "alice"
    )
    pid = new_project(owner="alice")
    
    # Priority 0
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r1.status_code == 422, r1.text
    
    # Priority 6
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r2.status_code == 422, r2.text
