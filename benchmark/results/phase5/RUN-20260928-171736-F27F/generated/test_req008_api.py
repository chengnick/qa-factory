import pytest

def test_tc1_owner_can_delete_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create a task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Delete the task as alice (owner)
    del_res = alice.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_tc2_task_creator_can_delete_task(as_user, new_project, user_ids):
    alice = as_user("alice")
    pid = new_project(owner="alice", members=("bob",))
    
    bob = as_user("bob")
    # Create a task as bob
    task_res = bob.post(f"/api/projects/{pid}/tasks", json={"title": "Task by bob"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Delete the task as bob (creator)
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 204, del_res.text

def test_tc3_other_member_cannot_delete_task(as_user, new_project, user_ids):
    alice = as_user(
        "alice"
    )  
    pid = new_project(owner="alice", members=("bob",))
    
    # Create task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()["id"]
    
    # Bob attempts to delete alice's task
    bob = as_user("bob")
    del_res = bob.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
    
    # Verify task still exists
    get_res = alice.get(f"/api/tasks/{tid}")
    assert get_res.status_code == 200, get_res.text

def test_tc4_non_member_cannot_delete_task(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Create task as alice
    task_res = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Task by alice"})
    assert task_res.status_code == 201, task_res.text
    tid = task_res.json()[
        "id"
    ]  
    
    # Carol (non-member) attempts to delete the task
    carol = as_user("carol")
    del_res = carol.delete(f"/api/tasks/{tid}")
    assert del_res.status_code == 403, del_res.text
