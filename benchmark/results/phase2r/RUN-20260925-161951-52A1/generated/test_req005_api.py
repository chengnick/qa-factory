import pytest

def test_req005_tc1_allowed_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Create task (status becomes todo)
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]
    assert task["status"] == "todo"

    # todo -> in_progress
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    # in_progress -> done
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # done -> todo (Wait, the requirements state: allowed transitions: todo -> in_progress, in_progress -> done, in_progress -> todo. Let's check TC-1 steps in requirement: todo -> in_progress, in_progress -> done, done -> todo? Wait, TC-1 steps say:
    # 1. POST /api/projects
    # 2. POST /api/projects/{pid}/tasks (todo)
    # 3. POST /api/tasks/{tid}/transition with to: in_progress
    # 4. POST /api/tasks/{tid}/transition with to: done
    # 5. POST /api/tasks/{tid}/transition with to: todo
    # Wait, if step 5 transitions from done to todo, does that succeed or fail? 
    # Let's re-read the prompt's TC-1 steps exactly:
    # "POST /api/tasks/{tid}/transition with {"to": "todo"} as alice" after done. 
    # Wait, TC-2 says: "done 為終態，從 done 出發的任何流轉應回傳 409 且任務狀態保持不變。"
    # Ah, let's look at TC-1 steps vs description. TC-1 expected: 允許的狀態流轉包含：todo → in_progress、in_progress → done、in_progress → todo。
    # Wait, "in_progress → todo" means transitioning from in_progress to todo. Let's check the steps in TC-1:
    # If step 4 is in_progress -> done, then step 5 to todo from done would violate TC-2. Wait, let's look at the exact steps given in TC-1 in the prompt:
    # 1. POST /api/projects
    # 2. POST /api/projects/{pid}/tasks
    # 3. to: in_progress
    # 4. to: done
    # 5. to: todo -> Wait, if step 5 is to: todo from done, that would fail with 409 according to TC-2. Let's trace how in_progress -> todo is tested. Usually in_progress -> todo is tested by going todo -> in_progress -> todo. 
    # Let's check TC-1 steps verbatim from prompt: 
    # - POST /api/projects with {"name": "P1"} as alice
    # - POST /api/projects/{pid}/tasks with {"title": "Task 1"} as alice (status becomes todo)
    # - POST /api/tasks/{tid}/transition with {"to": "in_progress"} as alice
    # - POST /api/tasks/{tid}/transition with {"to": "done"} as alice
    # - POST /api/tasks/{tid}/transition with {"to": "todo"} as alice
    # Wait! If step 5 is to: todo after done, let's see if the server allows it or returns 409. If the requirement says done is a terminal state (TC-2), then step 5 in TC-1 as written in the prompt might be a typo in the prompt's test plan steps, OR in_progress -> todo should be tested with a fresh task. Let's test in_progress -> todo with a fresh task or follow the exact steps if possible. But wait, if step 5 expects success or 409? TC-1 expected: 允許的狀態流轉包含：todo → in_progress、in_progress → done、in_progress → todo。
    # To test in_progress -> todo properly according to the expected text, we can test todo -> in_progress -> todo on a task or separate tasks.


def test_req005_tc1_specific_allowed(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    # Test todo -> in_progress -> done
    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task A"})
    tid = r.json()["id"]
    
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r.status_code == 200, r.text
    
    r = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # Test in_progress -> todo on another task
    r2 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task B"})
    tid2 = r2.json()["id"]
    
    alice.post(f"/api/tasks/{tid2}/transition", json={"to": "in_progress"})
    r_back = alice.post(f"/api/tasks/{tid2}/transition", json={"to": "todo"})
    assert r_back.status_code == 200, r_back.text
    assert r_back.json()["status"] == "todo"


def test_req005_tc2_done_is_terminal(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]

    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})

    # Attempting to transition from done to todo should return 409 and keep status unchanged
    r_trans = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r_trans.status_code == 409, r_trans.text

    # Attempting to transition from done to in_progress should return 409
    r_trans2 = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r_trans2.status_code == 409, r_trans2.text

    # Verify status is still done
    r_get = alice.get(f"/api/tasks/{tid}")
    assert r_get.status_code == 200
    assert r_get.json()["status"] == "done"


def test_req005_tc3_unlisted_transitions(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]

    # todo -> done is unlisted, should return 409
    r_trans = alice.post(f"/api/tasks/{tid}/transition", json={"to": "done"})
    assert r_trans.status_code == 409, r_trans.text
    assert alice.get(f"/api/tasks/{tid}").json()["status"] == "todo"

    # todo -> todo (same-status transition) should return 409
    r_same = alice.post(f"/api/tasks/{tid}/transition", json={"to": "todo"})
    assert r_same.status_code == 409, r_same.text

    # Move to in_progress
    alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})

    # in_progress -> in_progress (same-status transition) should return 409
    r_same2 = alice.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"})
    assert r_same2.status_code == 409, r_same2.text


def test_req005_tc4_invalid_status_value(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")

    r = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task 1"})
    tid = r.json()["id"]

    r_invalid = alice.post(f"/api/tasks/{tid}/transition", json={"to": "invalid_status"})
    assert r_invalid.status_code == 422, r_invalid.text
