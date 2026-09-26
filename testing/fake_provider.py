"""FakeProvider: the real Gemini adapter over a scripted fake google-genai client.

Provider failures (429, 5xx, timeouts, connection errors) go through the same error mapping as live runs,
so the PROVIDER-layer classification (rules R2-R4) is tested end to end without the network.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

import httpx
from google.genai import errors

from llm.adapters.gemini import GeminiClient


def api_error(code: int, message: str = "provider error") -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": message, "status": "X"}})


def response(text: str, prompt_tokens: int = 100, output_tokens: int = 20) -> Any:
    usage = SimpleNamespace(prompt_token_count=prompt_tokens, candidates_token_count=output_tokens, thoughts_token_count=0)
    return SimpleNamespace(text=text, usage_metadata=usage, model_version="fake-gemini", candidates=[])


RATE_LIMITED = "429"
OVERLOADED = "503"
TIMEOUT = "timeout"
UNREACHABLE = "unreachable"


class _Models:
    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls = 0

    def generate_content(self, **_: Any) -> Any:
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if item == RATE_LIMITED:
            raise api_error(429, "quota exceeded")
        if item == OVERLOADED:
            raise api_error(503, "This model is currently experiencing high demand")
        if item == TIMEOUT:
            raise httpx.ReadTimeout("read timed out")
        if item == UNREACHABLE:
            raise httpx.ConnectError("connection refused")
        return response(item) if isinstance(item, str) else item


class FakeProvider(GeminiClient):
    """Script items: a response text, or RATE_LIMITED / OVERLOADED / TIMEOUT / UNREACHABLE. The last item repeats."""

    def __init__(self, script: Iterable[Any], model: str = "fake-gemini") -> None:
        self.models = _Models(list(script))
        super().__init__(model, client=SimpleNamespace(models=self.models))
