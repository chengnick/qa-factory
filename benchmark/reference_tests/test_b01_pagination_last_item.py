"""REQ-003: paging through the task list with a fixed limit returns every task exactly once."""


def test_paging_to_the_end_returns_every_task_exactly_once(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()
    created = [alice.post(f"/api/projects/{pid}/tasks", json={"title": f"task {i}"}).json()["id"] for i in range(5)]

    seen, offset, total = [], 0, None
    while True:
        resp = alice.get(f"/api/projects/{pid}/tasks", params={"limit": 2, "offset": offset})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        total = body["total"]
        if not body["items"]:
            break
        seen += [t["id"] for t in body["items"]]
        offset += 2
        assert offset <= 10, "pagination did not terminate"

    assert total == 5
    assert seen == created, f"expected {created}, got {seen}"
