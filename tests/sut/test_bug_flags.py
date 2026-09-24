"""The SUT_BUGS flag mechanism itself: parsing, fail-fast, and per-request evaluation."""

import pytest
from fastapi.testclient import TestClient

from sut import bugs
from sut.app import create_app


@pytest.mark.parametrize("raw", [None, "", "  ", ",", " , "])
def test_unset_or_blank_means_clean_build(raw):
    assert bugs.parse(raw) == frozenset()


def test_parse_normalizes_case_whitespace_and_duplicates():
    assert bugs.parse(" b01 , B04,b01 ") == {"B01", "B04"}


def test_unknown_bug_id_is_rejected():
    with pytest.raises(ValueError, match="B99"):
        bugs.parse("B01,B99")


def test_is_enabled_reads_environment_on_every_call(monkeypatch):
    monkeypatch.setenv(bugs.ENV_VAR, "B02")
    assert bugs.is_enabled("B02") and not bugs.is_enabled("B01")
    monkeypatch.setenv(bugs.ENV_VAR, "")
    assert not bugs.is_enabled("B02")


def test_is_enabled_rejects_unknown_literal():
    with pytest.raises(KeyError):
        bugs.is_enabled("B99")


def test_app_refuses_to_start_with_unknown_bug(monkeypatch):
    monkeypatch.setenv(bugs.ENV_VAR, "B1")
    with pytest.raises(ValueError):
        create_app(":memory:")


def _done_to_in_progress(client: TestClient) -> int:
    h = {"X-User": "alice"}
    pid = client.post("/api/projects", json={"name": "p"}, headers=h).json()["id"]
    tid = client.post(f"/api/projects/{pid}/tasks", json={"title": "t"}, headers=h).json()["id"]
    for to in ("in_progress", "done"):
        client.post(f"/api/tasks/{tid}/transition", json={"to": to}, headers=h)
    return client.post(f"/api/tasks/{tid}/transition", json={"to": "in_progress"}, headers=h).status_code


def test_same_app_switches_behavior_with_flag(monkeypatch):
    monkeypatch.delenv(bugs.ENV_VAR, raising=False)
    client = TestClient(create_app(":memory:"))
    assert _done_to_in_progress(client) == 409
    monkeypatch.setenv(bugs.ENV_VAR, "B02")
    assert _done_to_in_progress(client) == 200


def test_health_does_not_leak_enabled_bugs(monkeypatch):
    monkeypatch.setenv(bugs.ENV_VAR, "B01,B02")
    body = TestClient(create_app(":memory:")).get("/health").text
    assert "B0" not in body


@pytest.mark.parametrize("bug_id", ["B05", "B10"])
def test_ui_bug_markers_never_leak_into_served_page(monkeypatch, bug_id):
    for raw in ("", bug_id):
        monkeypatch.setenv(bugs.ENV_VAR, raw)
        html = TestClient(create_app(":memory:")).get("/").text
        assert "/*@" not in html and "is_enabled" not in html and "B0" not in html and "B10" not in html
