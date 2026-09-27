"""Rule table (spec v3 §5.4, as amended in Phase 3). Order matters: the first matching rule wins.

Ordering principle: specific rules before general ones.
    R1-R4 -> R19 -> R20 -> R5-R7 -> R18 -> R9 -> R8 -> R17 -> R21 -> R14-R16 -> R10 -> R11 / R11U -> R12 -> R13

R17, R18, R11U (Phase 3) and R19-R21 (after Phase 3) are additions to the v3 table (see docs/spec.md §5.4):
    R17  a pytest / tool call timed out after its retries          -> HARNESS / TIMEOUT
    R18  the permission gate or the generated-code policy refused   -> AGENT / PERMISSION_DENIED
    R11U an assertion failed and no cross-validation was available  -> SUT / ASSERTION, unverified
    R19  LLM API key invalid or missing (401 / 403)                  -> ENV / PERMISSION_DENIED
    R20  LLM API rejected the request (other 4xx, e.g. 400)          -> HARNESS / HTTP_4XX
    R21  a tool could not reach its target (not the health check)   -> ENV / CONNECTION
R5 also covers an LLM response with no usable text (LLMEmptyResponseError).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from classification.observations import RUNNERS, Unit

# A 5xx only counts when it is part of the failed comparison itself (not e.g. digits in a timestamp).
_HTTP_5XX = re.compile(r"assert\s+5\d\d\s*==|==\s*5\d\d\b|<Response \[5\d\d")
_BROWSER_LAUNCH = re.compile(r"BrowserType\.launch|Executable doesn't exist|Failed to launch|browser has been closed", re.IGNORECASE)
_NAVIGATION_TIMEOUT = re.compile(r"page\.goto.*Timeout|Timeout.*page\.goto|Navigation timeout", re.IGNORECASE | re.DOTALL)
_LOCATOR_TIMEOUT = re.compile(r"Timeout", re.IGNORECASE)
_LOCATOR = re.compile(r"locator|expect|get_by_|wait_for", re.IGNORECASE)


@dataclass(frozen=True)
class Rule:
    id: str
    layer: str
    symptom: str | Callable[[Unit], str]
    description: str
    when: Callable[[Unit], bool]

    def symptom_for(self, unit: Unit) -> str:
        return self.symptom(unit) if callable(self.symptom) else self.symptom


def _exc(*names: str) -> Callable[[Unit], bool]:
    return lambda u: u.exception in names


def _assertion_symptom(u: Unit) -> str:
    return "HTTP_5XX" if _HTTP_5XX.search(u.message) else "ASSERTION"


RULES: tuple[Rule, ...] = (
    Rule("R1", "ENV", "CONNECTION", "SUT health check failed", lambda u: u.kind == "health"),
    Rule("R2", "PROVIDER", "RATE_LIMIT", "LLM API returned 429", lambda u: u.kind == "llm" and _exc("LLMRateLimitError")(u)),
    Rule("R3", "PROVIDER", "HTTP_5XX", "LLM API returned 5xx", lambda u: u.kind == "llm" and _exc("LLMUnavailableError")(u)),
    Rule(
        "R4", "PROVIDER", lambda u: "TIMEOUT" if u.exception == "LLMTimeoutError" else "CONNECTION",
        "LLM API timeout or connection failure", lambda u: u.kind == "llm" and _exc("LLMTimeoutError", "LLMConnectionError")(u),
    ),  # fmt: skip
    Rule("R19", "ENV", "PERMISSION_DENIED", "LLM API key invalid or missing (401 / 403)",
         lambda u: u.kind == "llm" and _exc("LLMConfigError")(u)),  # fmt: skip
    Rule("R20", "HARNESS", "HTTP_4XX", "LLM API rejected the request (4xx other than 401/403/408/429)",
         lambda u: u.kind == "llm" and _exc("LLMRequestError")(u)),  # fmt: skip
    Rule("R5", "AGENT", "INVALID_OUTPUT", "LLM output could not be parsed into the expected structure, or was empty",
         lambda u: (u.kind == "agent" and _exc("AgentOutputError")(u)) or (u.kind == "llm" and _exc("LLMEmptyResponseError")(u))),  # fmt: skip
    Rule("R6", "AGENT", "INVALID_OUTPUT", "unregistered tool, arguments not matching the schema, or a repeated failing call",
         lambda u: u.kind == "tool" and _exc("UnknownToolError", "ToolArgumentError", "RepeatedToolCallError")(u)),  # fmt: skip
    Rule("R7", "AGENT", "SCHEMA_MISMATCH", "handoff missing required fields (attributed to the upstream agent)",
         lambda u: u.kind == "agent" and _exc("HandoffError")(u)),  # fmt: skip
    Rule("R18", "AGENT", "PERMISSION_DENIED", "permission gate or generated-code policy refused the action",
         lambda u: u.kind == "tool" and _exc("PermissionDeniedError")(u)),  # fmt: skip
    Rule("R9", "TEST", "CRASH", "pytest collection error, ImportError or SyntaxError",
         lambda u: u.kind == "tool" and u.tool in RUNNERS and u.collection_error),  # fmt: skip
    Rule("R8", "HARNESS", "CRASH", "pytest exit code 2 / 3 / 4",
         lambda u: u.kind == "tool" and u.tool in RUNNERS and u.exit_code in (2, 3, 4)),  # fmt: skip
    Rule("R17", "HARNESS", "TIMEOUT", "pytest or tool call timed out after its retries",
         lambda u: u.kind == "tool" and _exc("ToolTimeoutError")(u)),  # fmt: skip
    Rule("R21", "ENV", "CONNECTION", "a tool could not reach its target (other than the SUT health check)",
         lambda u: u.kind == "tool" and _exc("ToolConnectionError")(u)),  # fmt: skip
    Rule("R14", "TEST", "TIMEOUT", "Playwright locator timeout while the page loads normally",
         lambda u: u.kind in ("test", "diff") and u.outcome == "ERROR" and u.health_ok is True
         and bool(_LOCATOR_TIMEOUT.search(u.message)) and bool(_LOCATOR.search(u.message)) and not _NAVIGATION_TIMEOUT.search(u.message)),  # fmt: skip
    Rule("R15", "ENV", "TIMEOUT", "Playwright navigation timeout and the SUT health check failed",
         lambda u: u.kind in ("test", "diff") and u.outcome == "ERROR" and u.health_ok is False and bool(_NAVIGATION_TIMEOUT.search(u.message))),  # fmt: skip
    Rule("R16", "ENV", "CRASH", "browser could not start",
         lambda u: u.kind in ("test", "diff") and u.outcome == "ERROR" and bool(_BROWSER_LAUNCH.search(u.message))),  # fmt: skip
    Rule("R10", "TEST", "CRASH", "test raised something other than AssertionError (or went missing in one build)",
         lambda u: (u.kind == "test" and u.outcome == "ERROR") or (u.kind == "diff" and u.decision_rule in ("R10", "MISSING"))),  # fmt: skip
    Rule("R11", "SUT", _assertion_symptom, "cross-validation: fails with the bug, passes on the clean build",
         lambda u: u.kind == "diff" and u.decision_rule == "R11"),  # fmt: skip
    Rule("R11U", "SUT", _assertion_symptom, "assertion failed; no clean build to compare (unverified)",
         lambda u: u.kind == "test" and u.outcome == "FAIL"),  # fmt: skip
    Rule("R12", "TEST", "ASSERTION", "cross-validation: fails on both builds (unrelated to the injected bug)",
         lambda u: u.kind == "diff" and u.decision_rule == "R12"),  # fmt: skip
    Rule("R13", "TEST", "ASSERTION", "cross-validation: passes with the bug, fails on the clean build",
         lambda u: u.kind == "diff" and u.decision_rule == "R13"),  # fmt: skip
)
