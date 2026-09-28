import pytest
import httpx

def test_tc1_search_case_insensitive(as_user):
    alice = as_user(
        "alice"
    )
    proj_res = alice.post("/api/projects", json={"name": "Project Alpha"})
    assert proj_res.status_code == 201, proj_res.text
    pid = proj_res.json()["id"]

    task_res = alice.post(
        f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"}
    )
    assert task_res.status_code == 201, task_res.text

    search_res = alice.get(f"/api/projects/{pid}/tasks?q=login")
    assert search_res.status_code == 200, search_res.text
    data = search_res.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Fix Login Bug"


def test_tc2_sql_wildcards_literal(as_user):
    alice = as_user("alice")
    proj_res = alice.post("/api/projects", json={"name": "Project Beta"})
    assert proj_res.status_code == 201, proj_res.text
    pid = proj_res.json()["id"]

    t1_res = alice.post(
        f"/api/projects/{pid}/tasks", json={"title": "100% complete"}
    )
    assert t1_res.status_code == 201, t1_res.text

    t2_res = alice.post(
        f"/api/projects/{pid}/tasks", json={"title": "task_one"}
    )
    assert t2_res.status_code == 201, t2_res.text

    # Searching for '%' literal
    res_pct = alice.get(f"/api/projects/{pid}/tasks?q=100%25")
    assert res_pct.status_code == 200, res_pct.text
    items_pct = res_pct.json()["items"]
    assert len(items_pct) == 1
    assert items_pct[0]["title"] == "100% complete"

    # Searching for '_' literal. If '_' was treated as wildcard, '_one' might match 'task_one' or others incorrectly depending on position,
    # but here query is '_one' and title is 'task_one'. Let's ensure it matches literally.
    res_und = alice.get(f"/api/projects/{pid}/tasks?q=_one")
    assert res_und.status_code == 200, res_und.text
    items_und = res_und.json()["items"]
    assert len(items_und) == 1
    assert items_und[0]["title"] == "task_one"


def test_tc3_search_status_pagination(as_user):
    alice = as_user("alice")
    proj_res = alice.post("/api/projects", json={"name": "Project Gamma"})
    assert proj_res.status_code == 201, proj_res.text
    pid = proj_res.json()["id"]

    # Create 3 tasks with 'Login'
    t1 = alice.post(
        f"/api/projects/{pid}/tasks", json={"title": "Report Login Issue"}
    )
    assert t1.status_code == 201, t1.text
    t1_id = t1.json()["id"]

    t2 = alice.post(
        f"/api/projects/{pid}/tasks", json={"title": "Login Screen Redesign"}
    )
    assert t2.status_code == 201, t2.text
    t2_id = t2.json()["id"]

    t3 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Login API"})
    assert t3.status_code == 201, t3.text

    # Transition task 2 to in_progress
    tr = alice.post(f"/api/tasks/{t2_id}/transition", json={"to": "in_progress"})
    assert tr.status_code == 200, tr.text

    # Also transition task 1 just to be sure we can filter status specifically
    tr1 = alice.post(f"/api/tasks/{t1_id}/transition", json={"to": "in_progress"})
    assert tr1.status_code == 200, tr1.text

    # Query with q=Login&status=in_progress&limit=1&offset=0
    q_res = alice.get(
        f"/api/projects/{pid}/tasks?q=Login&status=in_progress&limit=1&offset=0"
    )
    assert q_res.status_code == 200, q_res.text
    data = q_res.json()
    assert "items" in data
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "in_progress"
    assert "Login" in data["items"][0]["title"]
