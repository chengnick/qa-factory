import pytest

def test_tc1_limit_offset_validation(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Default limit/offset
    r = alice.get(f"/api/projects/{pid}/tasks")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["limit"] == 20
    assert data["offset"] == 0

    # Valid boundary limits
    r = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r.status_code == 200, r.text
    r = alice.get(f"/api/projects/{pid}/tasks?limit=100&offset=0")
    assert r.status_code == 200, r.text

    # Invalid limit=0 (too low)
    r = alice.get(f"/api/projects/{pid}/tasks?limit=0&offset=0")
    assert r.status_code == 422, r.text

    # Invalid limit=101 (too high)
    r = alice.get(f"/api/projects/{pid}/tasks?limit=101&offset=0")
    assert r.status_code == 422, r.text

    # Invalid offset=-1 (negative)
    r = alice.get(f"/api/projects/{pid}/tasks?limit=20&offset=-1")
    assert r.status_code == 422, r.text


def test_tc2_total_unaffected_by_pagination(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    for i in range(3):
        alice.post(f"/api/projects/{pid}/tasks", json={"title": f"Task {i}"})

    r = alice.get(f"/api/projects/{pid}/tasks?limit=1&offset=0")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 1
    assert data["total"] == 3


def test_tc3_sequential_paging(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    created_titles = ["Task A", "Task B", "Task C", "Task D"]
    for t in created_titles:
        alice.post(f"/api/projects/{pid}/tasks", json={"title": t})

    r1 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=0")
    assert r1.status_code == 200, r1.text
    page1 = r1.json()
    assert page1["total"] == 4
    assert len(page1["items"]) == 2

    r2 = alice.get(f"/api/projects/{pid}/tasks?limit=2&offset=2")
    assert r2.status_code == 200, r2.text
    page2 = r2.json()
    assert page2["total"] == 4
    assert len(page2["items"]) == 2

    item_ids_1 = [item["id"] for item in page1["items"]]
    item_ids_2 = [item["id"] for item in page2["items"]]

    # No duplication, no omission
    all_collected = item_ids_1 + item_ids_2
    assert len(set(all_collected)) == 4


def test_tc4_offset_greater_than_or_equal_to_total(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})

    r = alice.get(f"/api/projects/{pid}/tasks?limit=20&offset=999")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"] == []
