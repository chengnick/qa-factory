"""Live smoke test against the real Gemini API. Skipped unless QA_LIVE=1 and GEMINI_API_KEY is set."""

import json
import os
from pathlib import Path

import pytest

from app import load_env_file
from llm.client import Message

load_env_file(Path(__file__).resolve().parents[2] / ".env")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("QA_LIVE") != "1" or not os.environ.get("GEMINI_API_KEY"), reason="set QA_LIVE=1 and GEMINI_API_KEY"),
]


def test_gemini_returns_json_with_usage():
    from llm.adapters.gemini import GeminiClient

    response = GeminiClient().chat([Message("system", 'Answer with JSON only: {"answer": int}'), Message("user", "2+3?")])

    assert json.loads(response.content)["answer"] == 5
    assert response.input_tokens and response.output_tokens
