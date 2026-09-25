"""http_request tool: result shape and error mapping (mock transport, no network)."""

import httpx
import pytest

from tools.http_tool import HttpTool
from tools.registry import ToolArgumentError, ToolConnectionError, ToolTimeoutError


def _tool(handler) -> HttpTool:
    return HttpTool("http://sut.test", transport=httpx.MockTransport(handler))


def test_successful_request_records_method_route_status():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["user"] = request.headers.get("X-User")
        seen["body"] = request.content
        return httpx.Response(201, json={"id": 7})

    result = _tool(handler)(method="post", route="/api/projects", user="alice", json={"name": "p"})

    assert result.ok
    assert result.data == {"method": "POST", "route": "/api/projects", "status_code": 201}
    assert result.command == "POST /api/projects"
    assert seen == {"user": "alice", "body": b'{"name":"p"}'}


@pytest.mark.parametrize("status, ok", [(200, True), (404, False), (500, False)])
def test_ok_reflects_status(status, ok):
    result = _tool(lambda r: httpx.Response(status, text="x"))(method="GET", route="/health")
    assert result.ok is ok and result.data["status_code"] == status


def test_connection_failure_is_tool_connection_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ToolConnectionError):
        _tool(handler)(method="GET", route="/health")


def test_timeout_is_tool_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ToolTimeoutError):
        _tool(handler)(method="GET", route="/health")


@pytest.mark.parametrize("method, route", [("TRACE", "/health"), ("GET", "health"), ("GET", "http://evil.test/x")])
def test_bad_method_or_route_rejected(method, route):
    with pytest.raises(ToolArgumentError):
        _tool(lambda r: httpx.Response(200))(method=method, route=route)
