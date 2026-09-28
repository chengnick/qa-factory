import pytest


def test_tc1_out_of_range_limit_and_offset(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # limit=0
    r = alice.get(f"/api/projects/{pid}/tasks?limit=0")
    assert r.status_code == 422, r.text

    # limit=101
    r = alice.get(f"/api/projects/{pid}/tasks?limit=101")
    assert r.status_code == 422, r.text

    # offset=-1
    r = alice.get(f"/api/projects/{pid}/tasks?offset=-1")
    assert r.status_code == 422, r.text


def test_tc2_total_unaffected_by_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 3 tasks
    for i in range(3):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i+1}"})

    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["total"] == 3
    assert len(data1["items"]) == 1

    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=5&offset=1")
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["total"] == 3
    assert len(data2["items"]) == 2


def test_tc3_sequential_fetching_no_duplicates_or_omissions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 3 tasks
    created_ids = []
    for i in range(3):
        res = alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i+1}"})
        assert res.status_code == 201
        created_ids.append(res.json()["id"])

    # Fetch limit=2, offset=0
    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=0")
    assert r1.status_code == 200, r1.text
    items1 = r1.json()["items"]
    assert len(items1) == 2

    # Fetch limit=2, offset=2
    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=2")
    assert r2.status_code == 200, r2.text
    items2 = r2.json()["items"]
    assert len(items2) == 1

    all_fetched_ids = [t["id"] for t in items1] + [t["id"] for t in items2]
    assert sorted(all_fetched_ids) == sorted(created_ids)


def test_tc4_items_empty_when_offset_ge_total(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 2 tasks
    for i in range(2):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i+1}"})

    r = alice.get(f"/api/projects/{pid}/tasks?limit=20&offset=100")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert data["items"] == []
