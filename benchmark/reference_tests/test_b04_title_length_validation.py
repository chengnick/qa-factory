"""REQ-002: title is 1-100 characters; over-long titles are a 422, never a 5xx."""


def test_title_length_boundary(as_user, new_project):
    alice = as_user("alice")
    pid = new_project()

    at_limit = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 100})
    over_limit = alice.post(f"/api/projects/{pid}/tasks", json={"title": "a" * 101})

    assert at_limit.status_code == 201, at_limit.text
    assert over_limit.status_code == 422, f"expected 422, got {over_limit.status_code}: {over_limit.text}"
