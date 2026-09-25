import pytest

def test_tc1_member_can_read_project_tasks_and_task_detail(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create a task in the project
    task_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_resp.status_code == 201, task_resp.text
    tid = task_resp.json()["id"]
    
    # 1. GET /api/projects/{pid}
    r_proj = alice.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 200, r_proj.text
    
    # 2. GET /api/projects/{pid}/tasks
    r_tasks = alice.get(f"/api/projects/{pid}/tasks")
    assert r_tasks.status_code == 200, r_tasks.text
    
    # 3. GET /api/tasks/{tid}
    r_task = alice.get(f"/api/tasks/{tid}")
    assert r_task.status_code == 200, r_task.text

def test_tc2_non_member_forbidden_from_reading(as_user, new_project):
    alice = as_user("alice")
    dave = as_user("dave")
    pid = new_project(owner="alice", members=())
    
    # Create a task as alice
    task_resp = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert task_resp.status_code == 201, task_resp.text
    tid = task_resp.json()["id"]
    
    # 1. GET /api/projects/{pid} as dave
    r_proj = dave.get(f"/api/projects/{pid}")
    assert r_proj.status_code == 403, r_proj.text
    
    # 2. GET /api/projects/{pid}/tasks as dave
    r_tasks = dave.get(f"/api/projects/{pid}/tasks")
    assert r_tasks.status_code == 403, r_tasks.text
    
    # 3. GET /api/tasks/{tid} as dave
    r_task = dave.get(f"/api/tasks/{tid}")
    assert r_task.status_code == 403, r_task.text

def test_tc3_non_existent_task_returns_404(as_user):
    alice = as_user("alice")
    r = alice.get("/api/tasks/999999")
    assert r.status_code == 404, r.text
