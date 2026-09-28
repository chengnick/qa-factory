import pytest


def test_default_pagination_and_sorting(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a couple of tasks to verify sorting and defaults
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task A"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task B"})
    
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()
    
    assert data["limit"] == 20, r.text
    assert data["offset"] == 0, r.text
    assert "total" in data, r.text
    assert "items" in data, r.text
    
    items = data["items"]
    assert len(items) == 2, r.text
    # Verify sorted by task ID in ascending order
    assert items[0]["id"] < items[1]["id"], r.text


def test_limit_boundary_values(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # limit=0 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=0")
    assert r.status_code == 422, r.text
    
    # limit=1 -> 200
    r = alice.get(f"/api/projects/{pid}/tasks?limit=1")
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) <= 1
    
    # limit=100 -> 200
    r = alice.get(f"/api/projects/{pid}/tasks?limit=100")
    assert r.status_code == 200, r.text
    
    # limit=101 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=101")
    assert r.status_code == 422, r.text


def test_offset_boundary_and_invalid_values(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # offset=-1 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?offset=-1")
    assert r.status_code == 422, r.text
    
    # offset=0 -> 200
    r = alice.get(f"/api/projects/{pid}/tasks?offset=0")
    assert r.status_code == 200, r.text


def test_total_count_independence_from_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    
    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r1.status_code == 201 or r1.status_code == 200, r1.text
    total_1 = r1.json()["total"]
    
    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=5&offset=2")
    assert r2.status_code == 200, r2.text
    total_2 = r2.json()["total"]
    
    assert total_1 == total_2, f"Total changed with pagination: {total_1} vs {total_2}"
    assert total_1 == 2, r1.text


def test_offset_greater_than_or_equal_to_total_returns_empty(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    total = r.json()["total"]
    assert total == 1
    
    # Offset equal to total
    r_eq = alice.get(f"/api/projects/{pid}/tasks?offset={total}&limit=10")
    assert r_eq.status_code == 200, r_eq.text
    assert r_eq.json()["items"] == [], r_eq.text
    
    # Offset greater than total
    r_gt = alice.get(f"/api/projects/{pid}/tasks?offset={total + 5}&limit=10")
    assert r_gt.status_code == 200, r_gt.text
    assert r_gt.json()["items"] == [], r_gt.text
