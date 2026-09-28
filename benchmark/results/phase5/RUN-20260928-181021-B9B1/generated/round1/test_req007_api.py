def test_project_member_can_read_task_info(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Alice creates a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Test Task"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]
    
    # Alice gets project details
    proj_res = alice.get(f"/api/projects/{pid}")
    assert proj_res.status_code == 200, proj_res.text
    
    # Alice gets the task list
    list_res = alice.get(f"/api/projects/{pid}/tasks")
    assert list_res.status_code == 200, list_res.text
    tasks = list_res.json()["items"]
    assert any(t["id"] == tid for t in tasks)
    
    # Alice gets task details
    task_res = alice.get(f"/api/tasks/{tid}")
    assert task_res.status_code == 200, task_res.text
    assert task_res.json()["id"] == tid


def test_non_project_member_forbidden(as_user, new_project):
    alice = as_user("alice")
    bob = as_user("bob")
    pid = new_project(owner="alice")
    
    # Alice creates a task
    create_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Secret Task"})
    assert create_res.status_code == 201, create_res.text
    tid = create_res.json()["id"]
    
    # Bob attempts to get project details
    proj_res = bob.get(f"/api/projects/{pid}")
    assert proj_res.status_code == 403, proj_res.text
    
    # Bob attempts to get the task list
    list_res = bob.get(f"/api/projects/{pid}/tasks")
    assert list_res.status_code == 403, list_res.text
    
    # Bob attempts to get the task details
    task_res = bob.get(f"/api/tasks/{tid}")
    assert task_res.status_code == 403, task_res.text


def test_non_existent_resources_returns_404(as_user):
    alice = as_user("alice")
    
    # Alice requests task details for a non-existent task ID
    task_res = alice.get("/api/tasks/99999")
    assert task_res.status_code == 404, task_res.text
