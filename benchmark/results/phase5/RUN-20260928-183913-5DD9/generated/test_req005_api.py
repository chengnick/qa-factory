import pytest

def test_tc1_allowed_task_status_transitions(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    # Create task (status starts as todo)
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]
    assert task["status"] == "todo"
    
    # todo -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    
    # in_progress -> done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    
    # done -> todo is forbidden, but let's test in_progress -> todo separately or check specific allowed transitions.
    # Wait, the requirement says allowed transitions include: todo -> in_progress, in_progress -> done, in_progress -> todo.
    # Let's create another task to test in_progress -> todo.
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]
    
    r = client.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    r = client.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc2_forbidden_transitions_from_done(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    # todo -> in_progress -> done
    client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    
    # Attempt done -> in_progress
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text
    
    # Attempt done -> todo
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status remains done
    r = client.get(f"/api/tasks/{tid}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_tc3_unlisted_and_self_transitions_return_409(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Todo"})
    assert r.status_code == 201, r.text
    tid = r.json()[
        "id"
    ]
    
    # Self-transition: todo -> todo
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Unlisted transition: todo -> done
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text


def test_tc4_invalid_status_parameter_returns_422(as_user, new_project):
    client = as_user("alice")
    pid = new_project(owner="alice", members=())
    
    r = client.post(f"/api/projects/{pid}/tasks", json={"title": "Task Invalid"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
