import pytest

def test_tc1_limit_offset_validation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # limit=0 (out of range, limit must be 1-100)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 0})
    assert r.status_code == 422, r.text

    # limit=101 (out of range)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 101})
    assert r.status_code == 422, r.text

    # offset=-1 (must be >= 0)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"offset": -1})
    assert r.status_code == 422, r.text

def test_tc2_total_unaffected_by_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 3 tasks
    for i in range(3):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    r1 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 1, "offset": 0})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["total"] == 3
    assert len(data1["items"]) == 1

    r2 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 50, "offset": 0})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["total"] == 3
    assert len(data2["items"]) == 3

def test_tc3_sequential_fetching_fixed_limit(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 3 tasks
    created_ids = []
    for i in range(3):
        r = alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})
        assert r.status_code == 201
        created_ids.append(r.json()["id"])

    # Fetch page 1 (limit=2, offset=0)
    r1 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": 0})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    items1 = data1["items"]
    assert len(items1) == 2

    # Fetch page 2 (limit=2, offset=2)
    r2 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": 2})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    items2 = data2["items"]
    assert len(items2) == 1

    all_fetched_ids = [t["id"] for t in items1] + [t["id"] for t in items2]
    assert all_fetched_ids == created_ids

def test_tc4_empty_items_when_offset_ge_total(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 2 tasks
    for i in range(2):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    # Get total first
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200
    total = r.json()["total"]
    assert total == 2

    # offset equal to total
    r_eq = alice.get(f"/api/projects/{pid}/tasks", params={"offset": total})
    assert r_eq.status_code == 200, r_eq.text
    data_eq = r_eq.json()
    assert data_eq["items"] == []
    assert data_eq["total"] == total

    # offset greater than total
    r_gt = alice.get(f"/api/projects/{pid}/tasks", params={"offset": total + 5})
    assert r_gt.status_code == 200, r_gt.text
    data_gt = r_gt.json()
    assert data_gt["items"] == []
    assert data_gt["total"] == total
