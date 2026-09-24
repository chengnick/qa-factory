"""REQ-009: title search is case-insensitive."""


def test_search_ignores_case(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    tid = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Fix Login Bug"}).json()["id"]
    alice.post(f"/api/projects/{pid}/tasks", json={"title": "Write docs"})

    resp = alice.get(f"/api/projects/{pid}/tasks", params={"q": "login"})

    assert resp.status_code == 200, resp.text
    assert [t["id"] for t in resp.json()["items"]] == [tid]
