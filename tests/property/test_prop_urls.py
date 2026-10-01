"""Property 3: URLs that look like the SUT but are not (userinfo "@", an extra port digit, the SUT as a subdomain label,
a different scheme) are never allowed: not as an http_request route and not hard-coded in generated test code.
The SUT's own paths and URLs stay allowed (control)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.property.prop_support import SUT, SUT_ROUTES, gated_world, lookalike_routes, lookalike_urls
from tools.code_policy import check_source
from tools.registry import PermissionDeniedError


@given(route=lookalike_routes(), agent=st.sampled_from(["automation", "qa"]))
def test_http_request_refuses_lookalike_routes(route, agent):
    with gated_world() as w:
        with pytest.raises(PermissionDeniedError):
            w.gate.check(agent, "http_request", {"method": "GET", "route": route})


@given(route=SUT_ROUTES, agent=st.sampled_from(["automation", "qa"]))
def test_http_request_allows_sut_paths(route, agent):
    with gated_world() as w:
        w.gate.check(agent, "http_request", {"method": "GET", "route": route})


@given(url=lookalike_urls())
def test_static_check_flags_hardcoded_lookalike_urls(url):
    source = f"import httpx\n\nURL = {url!r}\n\n\ndef test_x():\n    assert httpx.get(URL)\n"
    kinds = [(v.kind, v.detail) for v in check_source(source, sut_url=SUT)]
    assert ("HARDCODED_URL", url) in kinds, f"{url!r} passed the generated-code policy as if it were the SUT"


@given(path=st.sampled_from(["", "/", "/api/tasks", "/health"]))
def test_static_check_accepts_the_sut_url(path):
    source = f"URL = {SUT + path!r}\n"
    assert not [v for v in check_source(source, sut_url=SUT) if v.kind == "HARDCODED_URL"]
