def test_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task (status is todo by default)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["status"] == "todo"

    # 1. todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # 2. in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Create another task to test in_progress -> todo
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 2"})
    assert r.status_code == 201, r.text
    tid2 = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text

    # 3. in_progress -> todo
    r = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "todo"


def test_tc2_forbidden_transition_from_done(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task Done"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # Move to in_progress then done
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Try to transition from done to todo
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text
    
    # Verify status remains done
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["status"] == "done"


def test_tc3_forbidden_transitions_various(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Task in todo status
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Todo Task"})
    tid_todo = r.json()["id"]

    # 1. todo -> done (forbidden -> 409)
    r = alice.post(f"/api/tasks/{tid_todo}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text

    # 2. todo -> todo (self-transition -> 409)
    r = alice.post(f"/api/tasks/{tid_todo}/transition", json={"to": "todo"})
    assert r.status_code == 409, r.text

    # Task in in_progress status
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "In Progress Task"})
    tid_ip = r.json()["id"]
    alice.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})

    # 3. in_progress -> in_progress (self-transition -> 409)
    r = alice.post(f"/api/tasks/{tid_ip}/transition", json={"to": "in_progress"})
    assert r.status_code == 409, r.text

    # Task in done status
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Done Task"})
    tid_done = r.json()["id"]
    alice.post(f"/api/tasks/{tid_done}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid_done}/transition", json={"to": "done"})

    # 4. done -> done (self-transition -> 409)
    r = alice.post(f"/api/tasks/{tid_done}/transition", json={"to": "done"})
    assert r.status_code == 409, r.text


def test_tc4_invalid_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Invalid Status Task"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r.status_code == 422, r.text
