"""Regression test for the hard-coded URL check (found by tests/property/test_prop_urls.py, fixed after Phase 5,
recorded as amendment A6): an allowlisted prefix only matches where a path, query or fragment begins."""

from __future__ import annotations

import pytest

from tools.code_policy import check_source

SUT = "http://127.0.0.1:8765"


def _flagged(url: str) -> bool:
    return any(v.kind == "HARDCODED_URL" for v in check_source(f"URL = {url!r}\n", sut_url=SUT))


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8765@evil.test/x", "http://127.0.0.1:8765@evil.test", "http://127.0.0.1:87650/x", "http://127.0.0.1:8765.evil.test/x",
     "http://127.0.0.1:8765evil/x", "https://127.0.0.1:8765/x"],
    ids=["userinfo", "userinfo-bare", "extra-port-digit", "subdomain", "glued", "other-scheme"],
)
def test_lookalikes_of_the_sut_are_flagged(url):
    assert _flagged(url)


@pytest.mark.parametrize("url", [SUT, SUT + "/", SUT + "/api/tasks", SUT + "?x=1", SUT + "#top"])
def test_the_sut_itself_is_still_allowed(url):
    assert not _flagged(url)
