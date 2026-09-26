"""GeminiClient against a fake google-genai client: request shape, usage, error mapping. No network."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

pytest.importorskip("google.genai")

from google.genai import errors  # noqa: E402

from llm.adapters import gemini  # noqa: E402
from llm.adapters.gemini import GEMINI_RETRY, GeminiClient
from llm.client import (
    LLMConfigError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    Message,
)
from observability.instrument import TracedLLM

FAKE_KEY = "AIzaSyA1234567890abcdefghijklmnopqrstuv"  # 39 chars, Google key shape; not a real key


@dataclass
class FakeModels:
    outcomes: list[Any]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _response(text: str | None = '{"ok": true}', prompt=120, candidates=30, thoughts=50, model_version="gemini-3.8-flash-001"):
    usage = SimpleNamespace(prompt_token_count=prompt, candidates_token_count=candidates, thoughts_token_count=thoughts)
    return SimpleNamespace(text=text, usage_metadata=usage, model_version=model_version, candidates=[SimpleNamespace(finish_reason="SAFETY")])


def _client(*outcomes: Any) -> tuple[GeminiClient, FakeModels]:
    models = FakeModels(list(outcomes))
    return GeminiClient("gemini-3.8-flash", client=SimpleNamespace(models=models)), models


def _api_error(code: int, message: str = "boom") -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": message, "status": "X"}})


MESSAGES = [Message("system", "be terse"), Message("system", "JSON only"), Message("user", "hello"), Message("assistant", "{}"), Message("user", "again")]


def test_request_uses_json_mode_fixed_temperature_and_system_instruction():
    llm, models = _client(_response())

    llm.chat(MESSAGES)

    (call,) = models.calls
    assert call["model"] == "gemini-3.8-flash"
    config = call["config"]
    assert config.temperature == 0.0
    assert config.response_mime_type == "application/json"
    assert config.system_instruction == "be terse\n\nJSON only"
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    assert [c.parts[0].text for c in call["contents"]] == ["hello", "{}", "again"]


def test_usage_maps_to_chat_response_including_thinking_tokens():
    llm, _ = _client(_response(prompt=120, candidates=30, thoughts=50))

    response = llm.chat([Message("user", "hi")])

    assert response.content == '{"ok": true}'
    assert response.model == "gemini-3.8-flash-001"
    assert (response.input_tokens, response.output_tokens) == (120, 80)


def test_missing_usage_is_none_not_zero():
    llm, _ = _client(SimpleNamespace(text="{}", usage_metadata=None, model_version=None, candidates=[]))

    response = llm.chat([Message("user", "hi")])

    assert response.input_tokens is None and response.output_tokens is None
    assert response.model == "gemini-3.8-flash"


@pytest.mark.parametrize(
    "error, expected",
    [
        (_api_error(429, "quota exceeded"), LLMRateLimitError),
        (_api_error(503), LLMUnavailableError),
        (_api_error(504), LLMTimeoutError),
        (_api_error(401), LLMConfigError),
        (_api_error(500), LLMUnavailableError),  # spec v3 R3: every provider 5xx is PROVIDER
        (_api_error(502), LLMUnavailableError),
        (_api_error(400), LLMError),
        (httpx.ReadTimeout("slow"), LLMTimeoutError),
        (httpx.ConnectError("refused"), LLMConnectionError),
    ],
)
def test_errors_map_to_llm_error_types(error, expected):
    llm, _ = _client(error)

    with pytest.raises(expected):
        llm.chat([Message("user", "hi")])


def test_rate_limit_is_not_mistaken_for_generic_error():
    llm, _ = _client(_api_error(429))
    with pytest.raises(LLMError) as exc_info:
        llm.chat([Message("user", "hi")])
    assert type(exc_info.value) is LLMRateLimitError


def test_empty_response_raises_with_finish_reason():
    llm, _ = _client(_response(text=None))

    with pytest.raises(LLMError, match="SAFETY"):
        llm.chat([Message("user", "hi")])


def test_api_key_never_appears_in_error_messages():
    llm, _ = _client(_api_error(400, f"API key not valid: {FAKE_KEY}"))

    with pytest.raises(LLMError) as exc_info:
        llm.chat([Message("user", "hi")])

    assert FAKE_KEY not in str(exc_info.value)


def test_missing_api_key_is_a_config_error(monkeypatch):
    monkeypatch.delenv(gemini.API_KEY_ENV, raising=False)

    with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
        GeminiClient()


def test_real_client_is_built_with_sdk_retries_disabled(monkeypatch):
    seen: dict[str, Any] = {}

    class RecordingClient:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(gemini.genai, "Client", RecordingClient)
    monkeypatch.setenv(gemini.API_KEY_ENV, FAKE_KEY)

    GeminiClient(timeout_s=30)

    assert seen["api_key"] == FAKE_KEY
    assert seen["http_options"].retry_options.attempts == 1
    assert seen["http_options"].timeout == 30_000


def test_rate_limit_retry_goes_through_with_retry(harness):
    llm, models = _client(_api_error(429), _api_error(429), _response())
    traced = TracedLLM(llm, harness.inst, GEMINI_RETRY)

    traced.chat([Message("user", "hi")])

    assert len(models.calls) == 3
    attempts = harness.named("attempt")
    assert len(attempts) == 3
    assert [a.attributes.get("qa.failure.symptom") for a in sorted(attempts, key=lambda s: s.attributes["qa.retry.attempt"])] == [
        "RATE_LIMIT",
        "RATE_LIMIT",
        None,
    ]
    assert harness.clock.sleeps == [5.0, 10.0]
    span = harness.one("llm.chat")
    assert span.attributes["gen_ai.request.temperature"] == 0.0
    assert span.attributes["gen_ai.usage.output_tokens"] == 80


def test_overloaded_model_is_retried(harness):
    llm, models = _client(_api_error(503, "high demand"), _response())

    TracedLLM(llm, harness.inst, GEMINI_RETRY).chat([Message("user", "hi")])

    assert len(models.calls) == 2
    assert harness.clock.sleeps == [5.0]
    first = min(harness.named("attempt"), key=lambda s: s.attributes["qa.retry.attempt"])
    assert first.attributes["qa.failure.symptom"] == "HTTP_5XX"


@pytest.mark.parametrize(
    "error, symptom, rule",
    [
        (_api_error(429), "RATE_LIMIT", "R2"),
        (_api_error(503), "HTTP_5XX", "R3"),
        (_api_error(500), "HTTP_5XX", "R3"),
        (httpx.ReadTimeout("slow"), "TIMEOUT", "R4"),
        (httpx.ConnectError("refused"), "CONNECTION", "R4"),
    ],
)
def test_provider_failures_are_layer_provider_and_env_blocked(harness, error, symptom, rule):
    llm, _ = _client(error)

    result = harness.run(llm=llm)

    assert result.verdict == "ENV_BLOCKED"
    llm_span = harness.one("llm.chat")
    assert llm_span.attributes["qa.failure.layer"] == "PROVIDER"
    assert llm_span.attributes["qa.failure.symptom"] == symptom
    assert llm_span.attributes["qa.failure.rule"] == rule
    assert harness.one("qa.run").attributes["qa.failure.layer"] == "PROVIDER"


def test_non_provider_llm_error_is_not_provider(harness):
    """A 400 is not a provider outage (R2-R4) and no v3 rule covers it: UNKNOWN -> INCONCLUSIVE."""
    llm, _ = _client(_api_error(400))

    result = harness.run(llm=llm)

    assert result.verdict == "INCONCLUSIVE"
    assert "qa.failure.layer" not in harness.one("llm.chat").attributes
