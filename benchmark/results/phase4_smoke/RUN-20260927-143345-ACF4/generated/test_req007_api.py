import pytest

def test_project_member_can_read_project_task_list_and_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Get project details
    proj_res = alice.get(f"/api/projects/{pid}")
    assert proj_res.status_code == 200, proj_res.text
    
    # Get task list
    list_res = alice.get(f"/api/projects/{pid}/tasks")
    assert list_res.status_code == 200, list_res.text
    assert len(list_res.json()["items"]) == 1
    
    # Get task detail
    detail_res = alice.get(f"/api/tasks/{tid}")
    assert detail_res.status_code == 200, detail_res.text
    assert detail_res.json()["id"] == tid


def test_non_project_member_is_forbidden_to_read(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice", members=())
    
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Bob attempts to read project
    proj_res = bob.get(f"/api/projects/{pid}")
    assert proj_res.status_code == 403, proj_res.text
    
    # Bob attempts to read task list
    list_res = bob.get(f"/api/projects/{pid}/tasks")
    assert list_res.status_code == 403, list_res.text
    
    # Bob attempts to read task detail
    detail_res = bob.get(f"/api/tasks/{tid}")
    assert detail_res.status_code == 403, detail_res.text


def test_system_returns_404_for_non_existent_resources(as_user):
    alice = as_user("alice")
    non_existent_id = 99999
    
    # Read non-existent project
    proj_res = alice.get(f"/api/projects/{non_existent_id}")
    assert proj_res.status_code == 404, proj_res.text
    
    # Read non-existent project task list
    list_res = alice.get(f"/api/projects/{non_existent_id}/tasks")
    assert list_res.status_code == 404, list_res.text
    
    # Read non-existent task detail
    detail_res = alice.get(f"/api/tasks/{non_existent_id}")
    assert detail_res.status_code == 404, detail_res.text
