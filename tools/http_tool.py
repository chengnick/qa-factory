"""http_request: a single black-box HTTP call to the SUT."""

from __future__ import annotations

from typing import Any

import httpx

from tools.registry import ToolArgumentError, ToolConnectionError, ToolResult, ToolTimeoutError

METHODS = {"GET", "POST", "PATCH", "PUT", "DELETE"}
BODY_LIMIT = 4000


class HttpTool:
    def __init__(self, base_url: str, *, timeout_s: float = 10.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport)

    def __call__(self, method: str, route: str, user: str | None = None, json: dict[str, Any] | None = None) -> ToolResult:
        method = method.upper()
        if method not in METHODS:
            raise ToolArgumentError(f"unsupported method {method!r}")
        if not route.startswith("/") or "://" in route:
            raise ToolArgumentError(f"route must be a path on the SUT, got {route!r}")
        headers = {"X-User": user} if user else {}
        try:
            resp = self._client.request(method, route, headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise ToolTimeoutError(f"{method} {route} timed out") from exc
        except httpx.TransportError as exc:
            raise ToolConnectionError(f"{method} {route}: {type(exc).__name__}: {exc}") from exc
        return ToolResult(
            ok=resp.status_code < 400,
            stdout=resp.text[:BODY_LIMIT],
            command=f"{method} {route}",
            data={"method": method, "route": route, "status_code": resp.status_code},
        )

    def close(self) -> None:
        self._client.close()
