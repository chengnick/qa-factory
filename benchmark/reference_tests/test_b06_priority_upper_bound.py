"""REQ-002: priority accepts 1-5 inclusive."""


def test_priority_upper_bound_is_inclusive(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()

    at_max = alice.post(f"/api/projects/{pid}/tasks", json={"title": "p5", "priority": 5})
    over_max = alice.post(f"/api/projects/{pid}/tasks", json={"title": "p6", "priority": 6})

    assert at_max.status_code == 201, at_max.text
    assert at_max.json()["priority"] == 5
    assert over_max.status_code == 422, over_max.text
