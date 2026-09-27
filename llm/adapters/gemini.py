"""Google Gemini adapter (google-genai SDK).

- API key comes from GEMINI_API_KEY only (never a CLI argument, never logged).
- The SDK's own retries are disabled: every retry must go through observability.with_retry().
- JSON output mode and a fixed temperature; token usage is mapped to ChatResponse.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from llm.client import (
    ChatResponse,
    LLMConfigError,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTimeoutError,
    LLMUnavailableError,
    Message,
)
from observability.redact import redact
from tools.registry import RetryPolicy

API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_TIMEOUT_S = 120.0

# Free-tier quotas are small and models get overloaded: back off generously on 429 / 503 / timeouts.
GEMINI_RETRY = RetryPolicy(max_attempts=5, retry_on=(LLMRateLimitError, LLMUnavailableError, LLMTimeoutError), backoff_s=5.0)


def _build_client(api_key: str, timeout_s: float) -> Any:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=int(timeout_s * 1000),  # milliseconds
            retry_options=types.HttpRetryOptions(attempts=1),  # 1 attempt = no SDK-level retries
        ),
    )


class GeminiClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        temperature: float = 0.0,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        if client is None:
            api_key = os.environ.get(API_KEY_ENV, "").strip()
            if not api_key:
                raise LLMConfigError(f"{API_KEY_ENV} is not set; put it in .env (see README)")
            client = _build_client(api_key, timeout_s)
        self._client = client
        self.model = model
        self.temperature = temperature

    def chat(self, messages: Sequence[Message]) -> ChatResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system") or None
        contents = [
            types.Content(role="model" if m.role == "assistant" else "user", parts=[types.Part(text=m.content)])
            for m in messages
            if m.role != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
        )
        try:
            response = self._client.models.generate_content(model=self.model, contents=contents, config=config)
        except errors.APIError as exc:
            raise _map_api_error(exc) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Gemini request timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise LLMConnectionError(f"cannot reach Gemini API: {type(exc).__name__}") from exc

        text = response.text
        if not text:
            reason = _finish_reason(response)
            raise LLMEmptyResponseError(f"Gemini returned no text (finish_reason={reason})")
        usage = response.usage_metadata
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = None
        if usage is not None and (usage.candidates_token_count is not None or usage.thoughts_token_count is not None):
            output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return ChatResponse(text, getattr(response, "model_version", None) or self.model, input_tokens, output_tokens)


def _map_api_error(exc: errors.APIError) -> LLMError:
    message = redact(f"Gemini API error {exc.code}: {exc.message}")
    if exc.code == 429:
        return LLMRateLimitError(message)
    if exc.code in (408, 504):
        return LLMTimeoutError(message)
    if exc.code >= 500:  # spec v3 R3: any provider 5xx is a PROVIDER failure
        return LLMUnavailableError(message)
    if exc.code in (401, 403):
        return LLMConfigError(message)
    if 400 <= exc.code < 500:
        return LLMRequestError(message)
    return LLMError(message)


def _finish_reason(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return str(reason) if reason is not None else "unknown"
