import pytest

def test_tc1_project_member_can_read(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]

    # GET /api/projects/{pid}
    res = alice.get(f"/api/projects/{pid}")
    assert res.status_code == 200, res.text

    # GET /api/projects/{pid}/tasks
    res = alice.get(f"/api/projects/{pid}/tasks")
    assert res.status_code == 200, res.text

    # GET /api/tasks/{tid}
    res = alice.get(f"/api/tasks/{tid}")
    assert res.status_code == 200, res.text


def test_tc2_non_member_cannot_read(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")

    # Alice creates a task
    res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert res.status_code == 201, res.text
    tid = res.json()["id"]

    # Bob tries to read project
    res = bob.get(f"/api/projects/{pid}")
    assert res.status_code == 403, res.text

    # Bob tries to read task list
    res = bob.get(f"/api/projects/{pid}/tasks")
    assert res.status_code == 403, res.text

    # Bob tries to read task detail
    res = bob.get(f"/api/tasks/{tid}")
    assert res.status_code == 403, res.text


def test_tc3_non_existent_resources_return_404(as_user):
    alice = as_user("alice")

    # Non-existent project
    res = alice.get("/api/projects/99999")
    assert res.status_code == 404, res.text

    # Non-existent project task list
    res = alice.get("/api/projects/99999/tasks")
    assert res.status_code == 404, res.text

    # Non-existent task detail
    res = alice.get("/api/tasks/99999")
    assert res.status_code == 404, res.text
