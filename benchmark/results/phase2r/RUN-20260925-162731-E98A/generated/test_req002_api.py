import pytest

def test_tc1_title_and_priority_boundary_values(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # 100-character title and priority 1 on POST
    title_100 = "a" * 100
    r_post = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_100, "priority": 1})
    assert r_post.status_code == 201, r_post.text
    task_data = r_post.json()
    tid = task_data["id"]
    assert task_data["title"] == title_100
    assert task_data["priority"] == 1
    
    # 1-character title and priority 5 on PATCH
    title_1 = "b"
    r_patch = alice.patch(f"/api/tasks/{tid}", json={"title": title_1, "priority": 5})
    assert r_patch.status_code == 200, r_patch.text
    updated_data = r_patch.json()
    assert updated_data["title"] == title_1
    assert updated_data["priority"] == 5

def test_tc2_invalid_title_lengths_and_blank_titles(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Empty string title
    r_empty = alice.post(f"/api/projects/{pid}/tasks", json={"title": "", "priority": 3})
    assert r_empty.status_code == 422, r_empty.text
    
    # 101-character title
    title_101 = "a" * 101
    r_long = alice.post(f"/api/projects/{pid}/tasks", json={"title": title_101, "priority": 3})
    assert r_long.status_code == 422, r_long.text

def test_tc3_out_of_range_priority_values(as_user, new_project):
    alice = as_user("alice")
    pid = new_project(owner="alice")
    
    # Priority 0
    r_p0 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 0})
    assert r_p0.status_code == 422, r_p0.text
    
    # Priority 6
    r_p6 = alice.post(f"/api/projects/{pid}/tasks", json={"title": "Valid Title", "priority": 6})
    assert r_p6.status_code == 422, r_p6.text
