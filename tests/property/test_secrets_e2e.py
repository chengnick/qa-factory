"""Secrets end to end: a FakeLLM run with real tools (SUT, pytest subprocess under L1a, Chromium), then every
saved file is scanned, junit XML, pytest logs, Playwright console.log and the unzipped trace.zip included.

Fixed examples rather than Hypothesis: one run takes tens of seconds. Synthetic secrets only, never a real LLM.

    configured   GEMINI_API_KEY / GITHUB_TOKEN / OPENAI_API_KEY values in the environment: in no file at all
                 (the pytest subprocess, and so the browser, only gets whitelisted variables)
    requirement  a GitHub-token-shaped secret in the requirement text: in no file at all
    header       a short Bearer value the test sends as a header (httpx and Playwright) and puts in its failure
    console      auth_token=... printed to the browser console
                 header and console are shapes redact() masks but the gate's secret scan does not detect, so the
                 test is written and run: they may stay in verbatim evidence only (prop_support.VERBATIM_EVIDENCE)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from prop_support import scan_saved_files

from evaluation import run as runner
from testing.fake_llm import FakeLLM

CONFIGURED = {"GEMINI_API_KEY": "E2eGeminiSynthetic0123456789abcdef", "GITHUB_TOKEN": "E2eGithubSynthetic0123456789abcdef",
              "OPENAI_API_KEY": "E2eOpenaiSynthetic0123456789abcdef"}  # fmt: skip
REQUIREMENT_SECRET = "ghp_E2eRequirementSynthetic01234567"
HEADER_VALUE = "HdrSynth0123"  # 12 characters: masked by redact(), below SECRET_SHAPES' 16 for Bearer
CONSOLE_VALUE = "Cons0lSynth9"  # auth_token=...: masked by redact(), not a SECRET_SHAPES key name

API_TEST = f'''
def test_header_reaches_the_sut(as_user):
    r = as_user("alice").get("/health", headers={{"Authorization": "Bearer {HEADER_VALUE}"}})
    assert r.status_code == 418, "sent Authorization: Bearer {HEADER_VALUE}"
'''

UI_TEST = f'''
def test_board_with_header(page, base_url):
    page.set_extra_http_headers({{"Authorization": "Bearer {HEADER_VALUE}"}})
    page.goto(base_url + "/?user=alice")
    page.evaluate("console.log('auth_token={CONSOLE_VALUE}')")
    assert page.title() == "no such title", "fail on purpose so the evidence is kept"
'''


def _llm() -> FakeLLM:
    requirement = {"summary": "The board loads for a known user", "acceptance_criteria": ["GET /health is 200", "the board renders"]}
    plan = {"cases": [{"id": "TC-1", "title": "health", "surface": "api", "steps": ["GET /health"], "expected": "200"},
                      {"id": "TC-2", "title": "board", "surface": "ui", "steps": ["open the board"], "expected": "rendered"}]}  # fmt: skip
    files = {"files": [{"path": "generated/test_req005_api.py", "surface": "api", "content": API_TEST},
                       {"path": "generated/test_req005_ui.py", "surface": "ui", "content": UI_TEST}]}  # fmt: skip
    return FakeLLM([json.dumps(requirement), json.dumps(plan), json.dumps(files)])


@pytest.fixture(scope="module")
def run_dir():
    assert not os.environ.get("QA_LIVE")
    with tempfile.TemporaryDirectory(prefix="qa-secrets-") as tmp:
        requirements = Path(tmp) / "requirements"
        requirements.mkdir()
        (requirements / "REQ-005.md").write_text(f"# REQ-005\n\nThe board loads.\n\nStaging token: {REQUIREMENT_SECRET}\n", encoding="utf-8")
        with mock.patch.dict(os.environ, CONFIGURED), mock.patch.object(runner, "REQUIREMENTS_DIR", requirements):
            llm = _llm()
            workspace, meta = runner.execute_run(requirement_id="REQ-005", sut_bugs=[], llm=llm, llm_kind="fake", model="fake-model",
                                                 artifacts_dir=Path(tmp) / "artifacts")  # fmt: skip
        assert isinstance(llm, FakeLLM) and llm.remaining == 0
        yield workspace, meta


@pytest.mark.ui
def test_the_run_produced_the_evidence_the_scan_must_cover(run_dir):
    workspace, meta = run_dir
    assert meta["differential"]["status"] == "COMPLETE", meta
    kinds = {p.relative_to(workspace).as_posix().split("/")[0] for p in workspace.rglob("*") if p.is_file()}
    assert {"reports", "pytest", "playwright", "generated", "spans", "prompts"} <= kinds
    assert list(workspace.glob("playwright/**/trace.zip")) and list(workspace.glob("playwright/**/console.log"))
    assert list(workspace.glob("reports/junit-*.xml")) and list(workspace.glob("pytest/*.log"))


@pytest.mark.ui
def test_configured_and_detected_secrets_are_in_no_saved_file(run_dir):
    workspace, _ = run_dir
    scan = scan_saved_files(workspace, [*CONFIGURED.values(), REQUIREMENT_SECRET])
    assert scan.unscanned == [], scan.unscanned
    assert scan.hits == [], scan.hits


@pytest.mark.ui
def test_masked_shapes_stay_only_in_verbatim_evidence(run_dir):
    workspace, _ = run_dir
    scan = scan_saved_files(workspace, [HEADER_VALUE, CONSOLE_VALUE])
    assert scan.unscanned == [], scan.unscanned
    assert scan.leaks() == [], scan.leaks()
    where = {w for w, _ in scan.hits}
    # the scan does reach into the evidence: Playwright records request headers and console output in trace.zip
    assert any(w.endswith("[trace.network]") for w in where), where
    assert any(w.endswith("console.log") for w in where), where
    assert any(w.startswith("reports/junit-") for w in where), where
