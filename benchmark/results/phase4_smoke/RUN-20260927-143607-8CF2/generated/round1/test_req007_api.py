import pytest

def test_tc1_member_reads_task_details(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    res_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert res_task.status_code == 201, res_task.text
    task_id = res_task.json()["id"]
    
    res_get = alice.get(f"/api/tasks/{task_id}")
    assert res_get.status_code == 200, res_get.text
    assert res_get.json()["id"] == task_id
    assert res_get.json()["title"] == "Task 1"

def test_tc2_non_member_receives_403(as_user, new_project, user_ids):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    res_task = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task B"})
    assert res_task.status_code == 201, res_task.text
    task_id = res_task.json()["id"]
    
    res_get = bob.get(f"/api/tasks/{task_id}")
    assert res_get.status_code == 403, res_get.text

def test_tc3_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    res_get = alice.get("/api/tasks/999999")
    assert res_get.status_code == 404, res_get.text
