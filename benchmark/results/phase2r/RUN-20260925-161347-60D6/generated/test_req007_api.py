import pytest

def test_tc1_project_member_can_read_project_tasks_and_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert create_res.status_code == 201, create_res.text
    task_data = create_res.json()
    tid = task_data["id"]

    # GET /api/projects/{pid}
    proj_res = alice.get(f"/api/projects/{pid}")
    assert proj_res.status_code == 200, proj_res.text

    # GET /api/projects/{pid}/tasks
    tasks_res = alice.get(f"/api/projects/{pid}/tasks")
    assert tasks_res.status_code == 200, tasks_res.text
    assert any(t["id"] == tid for t in tasks_res.json()["items"])

    # GET /api/tasks/{tid}
    detail_res = alice.get(f"/api/tasks/{tid}")
    assert detail_res.status_code == 200, detail_res.text
    assert detail_res.json()["id"] == tid


def test_tc2_non_member_receives_403_for_task_detail(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")

    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]

    # Bob is not a member, should get 403
    res = bob.get(f"/api/tasks/{tid}")
    assert res.status_code == 403, res.text


def test_tc3_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    res = alice.get("/api/tasks/999999")
    assert res.status_code == 404, res.text
