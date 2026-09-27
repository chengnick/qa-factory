"""Live tests are marked and are skipped without an API key (spec v3.1 §15.5.4).

These tests never start a live test in a subprocess: the guard is exercised directly on collected items,
so a mistake here cannot turn into a real API call.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import pytest_collection_modifyitems

REPO = Path(__file__).resolve().parents[2]


class _Item:
    def __init__(self, live: bool) -> None:
        self.live = live
        self.added: list = []

    def get_closest_marker(self, name: str):
        return object() if (name == "live" and self.live) else None

    def add_marker(self, marker) -> None:
        self.added.append(marker)


def test_guard_skips_live_items_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    live, normal = _Item(True), _Item(False)
    pytest_collection_modifyitems(None, [live, normal])
    assert [m.kwargs["reason"] for m in live.added] == ["live test: GEMINI_API_KEY is not set"]
    assert normal.added == []


def test_guard_leaves_live_items_alone_with_a_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "set-for-this-test-only")
    live = _Item(True)
    pytest_collection_modifyitems(None, [live])
    assert live.added == []


def test_live_module_does_not_load_env_at_import():
    """Loading .env at import would put the key back into the environment and defeat the guard."""
    tree = ast.parse((REPO / "tests/llm/test_gemini_live.py").read_text(encoding="utf-8"))
    top_level_calls = [n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    assert top_level_calls == []
    assert "load_env_file" not in (REPO / "tests/llm/test_gemini_live.py").read_text(encoding="utf-8")


def test_ci_marker_expression_deselects_live_tests():
    """Collection only (--collect-only): nothing is executed, and no key or QA_LIVE is in the environment."""
    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "QA_LIVE")}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    cmd = [sys.executable, "-m", "pytest", "tests/llm/test_gemini_live.py", "-m", "not live", "--collect-only", "-q", "-p", "no:cacheprovider"]
    out = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env).stdout
    assert "1 deselected" in out


def test_every_test_calling_the_real_client_is_marked_live():
    """A test that calls .chat() on a GeminiClient built without a fake client reaches the network."""
    offenders = []
    for path in (REPO / "tests").rglob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        if "GeminiClient()." in text and "pytest.mark.live" not in text:
            offenders.append(path.relative_to(REPO).as_posix())
    assert offenders == []


@pytest.mark.parametrize("marker", ["live"])
def test_marker_is_registered(marker):
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{marker}:' in text
