import pytest

def test_req003_tc1_default_pagination_and_boundaries(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # GET /api/projects/{pid}/tasks without limit or offset -> limit defaults to 20, offset to 0
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 20, r.text
    assert data["offset"] == 0, r.text

    # limit=0 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=0")
    assert r.status_code == 422, r.text

    # limit=101 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?limit=101")
    assert r.status_code == 422, r.text

    # offset=-1 -> 422
    r = alice.get(f"/api/projects/{pid}/tasks?offset=-1")
    assert r.status_code == 422, r.text


def test_req003_tc2_total_count_unaffected_by_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 3 tasks
    for i in range(3):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert len(d1["items"]) == 1
    assert d1["total"] == 3
    assert d1["limit"] == 1
    assert d1["offset"] == 0

    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=5&offset=1")
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert len(d2["items"]) == 2
    assert d2["total"] == 3
    assert d2["limit"] == 5
    assert d2["offset"] == 1


def test_req003_tc3_sequential_fetching(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 5 tasks
    created_ids = []
    for i in range(5):
        res = alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})
        assert res.status_code == 201
        created_ids.append(res.json()["id"])

    fetched_tasks = []
    limit = 2
    offset = 0
    while True:
        r = alice.get(f"/api/projects/{pid}/tasks?limit={limit}&offset={offset}")
        assert r.status_code == 200, r.text
        data = r.json()
        items = data["items"]
        fetched_tasks.extend(items)
        if len(items) < limit:
            break
        offset += limit

    assert len(fetched_tasks) == 5
    assert [t["id"] for t in fetched_tasks] == created_ids


def test_req003_tc4_offset_greater_than_or_equal_to_total(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create 2 tasks
    for i in range(2):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    # offset equals total (offset=2)
    r = alice.get(f"/api/projects/{pid}/tasks?offset=2")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert data["items"] == []

    # offset greater than total (offset=5)
    r = alice.get(f"/api/projects/{pid}/tasks?offset=5")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert data["items"] == []
