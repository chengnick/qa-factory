import pytest

def test_req009_tc1_case_insensitive_search(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Other task"})
    
    r = alice.get(f"/api/projects/{pid}/tasks", params={"q": "login"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data["items"]
    assert data["items"][0]["title"] == "Fix Login Bug"

def test_req009_tc2_literal_percent_and_underscore(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "50%_complete task"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "50X_complete task"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "50x0complete task"})
    
    r = alice.get(f"/api/projects/{pid}/tasks", params={"q": "50%_complete"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1, data["items"]
    assert data["items"][0]["title"] == "50%_complete task"

def test_req009_tc3_search_status_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Bug one"})
    t2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Bug two"}).json()
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Feature bug"})
    
    alice.post(f"/api/projects/{pid}/tasks/{t2['id']}/transition", json={"to": "in_progress"})
    
    r = alice.get(f"/api/projects/{pid}/tasks", params={"q": "Bug", "status": "todo", "limit": 10, "offset": 0})
    assert r.status_code == 200, r.text
    data = r.json()
    titles = [item["title"] for item in data["items"]]
    assert "Bug two" not in titles
    assert "Bug one" in titles
    assert "Feature bug" in titles
    assert data["total"] == 2
