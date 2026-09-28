import pytest

def test_req009_tc1_search_case_insensitivity(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task with mixed case title
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r.status_code == 201, r.text
    
    # Search with lower case query
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Fix Login Bug"

def test_req009_tc2_search_wildcard_literal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create tasks containing literal '%' and '_'
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 100% complete"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task_underscore"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task normal"})
    
    # Search for literal '%'
    r = alice.get(f"/api/projects/{pid}/tasks?q=%25")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Task 100% complete"
    
    # Search for literal '_'
    r = alice.get(f"/api/projects/{pid}/tasks?q=_")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data
    assert data["items"][0]["title"] == "Task_underscore"

def test_req009_tc3_search_combined_with_status_and_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create multiple tasks matching and not matching the criteria
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Bug fix A"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Bug fix B"})
    # Transition one task to 'in_progress' so it doesn't match status=todo
    t_in_progress = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Bug fix C"}).json()
    alice.post(f"/api/tasks/{t_in_progress['id']}/transition", json={"to": "in_progress"})
    
    # Search with q=Bug, status=todo, limit=1, offset=0
    r = alice.get(f"/api/projects/{pid}/tasks?q=Bug&status=todo&limit=1&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "todo"
    assert "Bug" in data["items"][0]["title"]
