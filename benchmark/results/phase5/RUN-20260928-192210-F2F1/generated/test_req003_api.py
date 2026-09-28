import pytest

def test_tc1_pagination_boundaries_and_defaults(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # limit=0 (out of range -> 422)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 0})
    assert r.status_code == 422, r.text

    # limit=101 (out of range -> 422)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 101})
    assert r.status_code == 422, r.text

    # offset=-1 (out of range -> 422)
    r = alice.get(f"/api/projects/{pid}/tasks", params={"offset": -1})
    assert r.status_code == 422, r.text

    # no limit and offset parameters -> defaults to limit=20, offset=0
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 20
    assert data["offset"] == 0

def test_tc2_total_count_regardless_of_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    for i in range(5):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    r = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": 0})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

def test_tc3_sequential_fetching_no_duplication_or_omission(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    task_ids = []
    for i in range(3):
        r = alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})
        assert r.status_code == 201, r.text
        task_ids.append(r.json()["id"])

    # Fetch limit=2, offset=0
    r1 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": 0})
    assert r1.status_code == 200, r1.text
    page1 = r1.json()

    # Fetch limit=2, offset=2
    r2 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": 2})
    assert r2.status_code == 200, r2.text
    page2 = r2.json()

    items1 = page1["items"]
    items2 = page2["items"]

    assert len(items1) == 2
    assert len(items2) == 1

    fetched_ids = [t["id"] for t in items1] + [t["id"] for t in items2]
    assert fetched_ids == task_ids

    # Ensure ascending order by task id
    assert fetched_ids == sorted(fetched_ids)

def test_tc4_empty_array_when_offset_ge_total(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    for i in range(2):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    # offset=2 (offset == total)
    r1 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 10, "offset": 2})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["total"] == 2
    assert data1["items"] == []

    # offset=5 (offset > total)
    r2 = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 10, "offset": 5})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["total"] == 2
    assert data2["items"] == []
