"""An exception that aborts the pipeline maps to a verdict by its type, not blanket AGENT_FAILED."""

import pytest
from opentelemetry.trace import StatusCode

from agents.base import AgentOutputError
from agents.report import exception_verdict
from llm.client import (
    LLMConfigError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from testing.fake_llm import FakeLLM
from tools.registry import ToolArgumentError, ToolConnectionError, ToolError, ToolTimeoutError, UnknownToolError


@pytest.mark.parametrize(
    "exc, verdict",
    [
        (LLMRateLimitError("429"), "ENV_BLOCKED"),
        (LLMUnavailableError("503"), "ENV_BLOCKED"),
        (LLMTimeoutError("slow"), "ENV_BLOCKED"),
        (LLMConnectionError("down"), "ENV_BLOCKED"),
        (LLMConfigError("401"), "ENV_BLOCKED"),
        (ToolTimeoutError("slow"), "ENV_BLOCKED"),
        (ToolConnectionError("down"), "ENV_BLOCKED"),
        (AgentOutputError("not json"), "AGENT_FAILED"),
        (UnknownToolError("rm_rf"), "AGENT_FAILED"),
        (ToolArgumentError("bad"), "AGENT_FAILED"),
        (LLMError("empty response"), "AGENT_FAILED"),
        (ToolError("file_write failed"), "TEST_BROKEN"),
        (RuntimeError("our bug"), None),
        (KeyError("x"), None),
    ],
    ids=lambda v: type(v).__name__ if isinstance(v, BaseException) else str(v),
)
def test_exception_verdict(exc, verdict):
    assert exception_verdict(exc) == verdict


@pytest.mark.parametrize("error", [LLMRateLimitError("429 quota"), LLMUnavailableError("503 high demand")])
def test_provider_overload_ends_run_env_blocked(harness, error):
    result = harness.run(llm=FakeLLM([error]))

    assert result.verdict == "ENV_BLOCKED"
    root = harness.one("qa.run")
    assert root.attributes["qa.verdict"] == "ENV_BLOCKED"
    assert root.status.status_code is StatusCode.ERROR


def test_invalid_llm_output_is_agent_failed(harness):
    assert harness.run(llm=FakeLLM(["not json"])).verdict == "AGENT_FAILED"


def test_unclassified_exception_propagates_and_trace_still_records_it(harness):
    with pytest.raises(RuntimeError, match="our bug"):
        harness.run(llm=FakeLLM([RuntimeError("our bug")]))

    root = harness.one("qa.run")
    assert root.status.status_code is StatusCode.ERROR
    assert "qa.verdict" not in root.attributes
