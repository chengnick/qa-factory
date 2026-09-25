"""Provisional verdict rules (Phase 1-2), until classification/verdict.py lands in Phase 3."""

import pytest

from agents.contracts import QAResult, ToolExecution
from agents.report import provisional_verdict

HEALTHY = ToolExecution("http_request", ok=True, attempts=1)


def _pytest(ok=True, exit_code=0, attempts=1, **data):
    return ToolExecution("pytest", ok=ok, attempts=attempts, exit_code=exit_code, data=data)


@pytest.mark.parametrize(
    "executions, verdict",
    [
        ([_pytest(), HEALTHY], "PASS"),
        ([_pytest(attempts=2), HEALTHY], "FLAKY"),
        ([_pytest(ok=False, exit_code=1, failures=1, assertion_failures=1), HEALTHY], "DEFECT_FOUND"),
        ([_pytest(ok=False, exit_code=1, failures=1, exception_failures=1), HEALTHY], "TEST_BROKEN"),
        ([_pytest(ok=False, exit_code=1, failures=2, assertion_failures=1, exception_failures=1), HEALTHY], "TEST_BROKEN"),
        ([_pytest(ok=False, exit_code=1, errors=1), HEALTHY], "TEST_BROKEN"),
        ([_pytest(ok=False, exit_code=2), HEALTHY], "TEST_BROKEN"),
        ([_pytest(ok=False, exit_code=1, assertion_failures=1), ToolExecution("http_request", ok=False, attempts=1)], "ENV_BLOCKED"),
        ([ToolExecution("pytest", ok=False, attempts=3, error="ToolTimeoutError: slow"), HEALTHY], "ENV_BLOCKED"),
    ],
)
def test_provisional_verdict(executions, verdict):
    assert provisional_verdict(QAResult("REQ-X", tuple(executions))) == verdict
