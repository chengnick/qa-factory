"""Properties: a secret never survives in a file a run saves (in-process runs, FakeLLM, synthetic secrets).

    P1 exact value   the value of a configured secret (GEMINI_API_KEY and two others, set in the environment)
                     appears in no saved file
    P2 known format  a secret in a format observability/redact.py masks, injected through the requirement text,
                     a tool input, a tool output, an exception message or an HTTP header in a tool result,
                     appears unmasked in no saved file, except verbatim evidence (generated tests, junit XML,
                     Playwright evidence): there only no string the gate's secret scan detects (prop_support.VERBATIM_EVIDENCE)

Out of scope: secrets of arbitrary format, and text inside images. The run follows app._run_fake (the same
writers: meta, classification, security events, rounds, workflow, report.json); real pytest, SUT and browser
are covered by test_secrets_e2e.py. Never run against a real LLM: every run asserts it uses FakeLLM.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

from hypothesis import given
from hypothesis import strategies as st
from prop_support import exact_secrets, format_secrets, scan_saved_files

from agents.contracts import RequirementInput
from evaluation.run import (
    base_meta,
    instrumentation,
    record_classification,
    record_policy,
    record_rounds,
    record_security,
    record_workflow,
    write_meta,
)
from llm.client import LLMError
from permissions.policy import default_policy
from pipeline import run_pipeline
from testing.fake_clock import FakeClock
from testing.fake_llm import FakeLLM
from testing.fake_tool import FakeTool
from tools.file_tool import FileWriteTool
from tools.pytest_tool import junit_tests
from tools.registry import ToolError, ToolRegistry, ToolResult

REQ = "REQ-005"
API_FILE = "generated/test_req005_api.py"
CONFIGURED = ("GEMINI_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY")
INJECTION_POINTS = ("requirement", "tool_input", "tool_output", "exception_tool", "exception_llm", "http_header")
HEALTH = ToolResult(ok=True, command="GET /health", data={"method": "GET", "route": "/health", "status_code": 200})


def _passed(stdout: str = "1 passed in 0.10s") -> ToolResult:
    return ToolResult(ok=True, exit_code=0, command=f"pytest {API_FILE}", stdout=stdout,
                      data={"results": [{"node_id": f"{API_FILE}::test_rule", "outcome": "PASS", "message": ""}]})  # fmt: skip


def _failed(text: str) -> ToolResult:
    """What PytestTool returns for a failing test: the results come from the real junit parser, which redacts."""
    message = f"AssertionError: expected 409, got 200; request had {text}"
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        suite = ElementTree.SubElement(ElementTree.Element("testsuites"), "testsuite")
        case = ElementTree.SubElement(suite, "testcase", classname="generated.test_req005_api", name="test_rule")
        ElementTree.SubElement(case, "failure", message=message).text = f"E   {message}"
        ElementTree.ElementTree(suite).write(junit, encoding="utf-8")
        results = junit_tests(junit, Path(tmp))
    return ToolResult(ok=False, exit_code=1, command=f"pytest {API_FILE}", stdout=f"E   {message}\n1 failed in 0.20s",
                      data={"results": results})  # fmt: skip


def _llm_script(test_source: str, *, automation_error: str | None = None) -> list:
    requirement = {"summary": "Duplicate task titles are rejected", "acceptance_criteria": ["POST returns 409 for a duplicate"]}
    plan = {"cases": [{"id": "TC-1", "title": "duplicate rejected", "surface": "api", "steps": ["post twice"], "expected": "409"}]}
    files = {"files": [{"path": API_FILE, "surface": "api", "content": test_source}]}
    third = LLMError(automation_error) if automation_error else json.dumps(files)
    return [json.dumps(requirement), json.dumps(plan), third]


def _tools(pytest_script: list, http_script: list) -> Callable[[Path], ToolRegistry]:
    def build(workspace: Path) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register("file_write", FileWriteTool(workspace))
        registry.register("pytest", FakeTool(pytest_script))
        registry.register("http_request", FakeTool(http_script))
        registry.register("playwright", FakeTool([_passed()]))
        return registry

    return build


def fake_run(root: Path, requirement_text: str, llm: FakeLLM, tools: Callable[[Path], ToolRegistry]) -> Path:
    """app._run_fake with a given requirement text, LLM script and tools; returns the run directory."""
    assert isinstance(llm, FakeLLM) and not os.environ.get("QA_LIVE")  # synthetic secrets never meet a real LLM
    from tools.workspace import create_run_workspace, new_run_id

    policy = default_policy()
    run_id = new_run_id()
    workspace = create_run_workspace(root, run_id)
    meta = base_meta(run_id, REQ, llm="fake", model="fake-model", temperature=None, sut_bugs=[], policy=policy)
    with instrumentation(workspace, FakeClock()) as inst:
        result = run_pipeline(RequirementInput(REQ, requirement_text), llm=llm, tools=tools(workspace), inst=inst,
                              run_id=run_id, dataset=meta["dataset"], workspace=workspace, policy=policy)  # fmt: skip
    meta.update(trace_id=result.trace_id, trace_file="trace.json", verdict=result.verdict, surface_verdict=result.surface_verdict,
                error=result.error, generated_files=[])  # fmt: skip
    record_classification(workspace, meta, result.classification, result.underlying_verdict)
    record_security(workspace, meta, result.security)
    record_policy(meta, result.policy)
    record_rounds(workspace, meta, result.rounds)
    write_meta(workspace, meta)
    record_workflow(workspace, meta, result.workflow)
    return workspace


def injected_run(root: Path, point: str, text: str) -> Path:
    """One run with `text` entering at `point`; everything else is an ordinary passing or failing run."""
    requirement = "# REQ-005\n\nDuplicate task titles in a project are rejected with 409.\n"
    source = "def test_rule(as_user):\n    assert as_user('alice').get('/health').status_code == 200\n"
    pytest_script: list = [_passed()]
    http_script: list = [HEALTH]
    automation_error = None
    if point == "requirement":
        requirement += f"\nStaging credential: {text}\n"
    elif point == "tool_input":  # the model copied it into the test it wrote
        source = f"# staging credential: {text}\n" + source
    elif point == "tool_output":
        pytest_script = [_failed(text)]
    elif point == "exception_tool":
        pytest_script = [ToolError(f"runner crashed while sending {text}")]
    elif point == "exception_llm":
        automation_error = f"provider said: invalid request with {text}"
    elif point == "http_header":
        # HttpTool's shape: the response text in stdout, only method / route / status in data
        http_script = [ToolResult(ok=True, command="GET /health", stdout=f'{{"status": "ok", "echo": {{"Authorization": "{text}"}}}}',
                                  data={"method": "GET", "route": "/health", "status_code": 200})]  # fmt: skip
    llm = FakeLLM(_llm_script(source, automation_error=automation_error))
    return fake_run(root, requirement, llm, _tools(pytest_script, http_script))


@given(secret=format_secrets, point=st.sampled_from(INJECTION_POINTS))
def test_a_secret_in_a_known_format_is_masked_in_every_saved_file(secret, point):
    name, (text, value) = secret
    with tempfile.TemporaryDirectory(prefix="qa-prop-") as tmp:
        scan = scan_saved_files(injected_run(Path(tmp), point, text), [value])
    assert scan.unscanned == [], scan.unscanned
    assert scan.leaks() == [], f"{name} secret {text!r} injected via {point} survives in: {scan.leaks()}"


@given(values=st.tuples(exact_secrets, exact_secrets, exact_secrets), point=st.sampled_from(INJECTION_POINTS))
def test_the_value_of_a_configured_secret_is_in_no_saved_file(values, point):
    """Configured secrets live in the environment; nothing the run saves may contain their values."""
    env = dict(zip(CONFIGURED, values, strict=True))
    with tempfile.TemporaryDirectory(prefix="qa-prop-") as tmp, mock.patch.dict(os.environ, env):
        # a run that also carries an unrelated known-format secret, so the masking paths are exercised too
        workspace = injected_run(Path(tmp), point, "Bearer unrelatedSynthetic0123")
        scan = scan_saved_files(workspace, list(values))
    assert scan.unscanned == [], scan.unscanned
    assert scan.hits == [], f"configured secret value found in: {scan.hits}"  # exact values: no exception anywhere
