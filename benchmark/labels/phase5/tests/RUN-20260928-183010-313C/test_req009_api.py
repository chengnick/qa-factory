import pytest
import httpx

def test_req009_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create tasks
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    assert r1.status_code == 201, r1.text
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Other Task"})
    assert r2.status_code == 201, r2.text
    
    # Search case-insensitively
    r = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["items"]
    assert len(items) == 1, f"Expected 1 task, got {items}"
    assert items[0]["title"] == "Fix Login Bug"

def test_req009_tc2_literal_percent_and_underscore(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create tasks containing '%' and '_'
    r1 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "100% finished"})
    assert r1.status_code == 201, r1.text
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "test_task"})
    assert r2.status_code == 201, r2.text
    r3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "testAtask"})
    assert r3.status_code == 201, r3.text
    
    # Query with '%'
    r_pct = alice.get(f"/api/projects/{pid}/tasks?q=100%")
    assert r_pct.status_code == 200, r_pct.text
    pct_items = r_pct.json()["items"]
    assert len(pct_items) == 1
    assert pct_items[0]["title"] == "100% finished"
    
    # Query with '_'
    r_under = alice.get(f"/api/projects/{pid}/tasks?q=test_task")
    assert r_under.status_code == 200, r_under.text
    under_items = r_under.json()["items"]
    assert len(under_items) == 1
    assert under_items[0]["title"] == "test_task"

def test_req009_tc3_simultaneous_search_status_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create tasks matching and not matching criteria
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task One"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Two"})
    r_todo = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Three"})
    assert r_todo.status_code == 201
    tid_three = r_todo.json()["id"]
    
    # Transition Task Three to in_progress
    alice.post(f"/api/tasks/{tid_three}/transition", json={"to": "in_progress"})
    
    # GET with q=Task&status=todo&limit=10&offset=0
    r = alice.get(f"/api/projects/{pid}/tasks?q=Task&status=todo&limit=10&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["items"]
    
    # Task One and Task Two should be todo and match 'Task'
    # Task Three is in_progress so it should be filtered out by status=todo
    titles = [item["title"] for item in items]
    assert "Task One" in titles
    assert "Task Two" in titles
    assert "Task Three" not in titles
    assert data["total"] == 2
