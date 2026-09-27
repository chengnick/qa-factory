"""Windows 8.3 short paths (GitHub's Windows runner has TEMP = C:\\Users\\RUNNER~1\\...): a workspace given in its short
form must work like the long form. resolve() returns the long form, so tools compare against a resolved root."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

from tools.file_tool import FileWriteTool
from tools.pytest_tool import PytestTool
from tools.workspace import create_run_workspace, new_run_id

pytestmark = pytest.mark.skipif(os.name != "nt", reason="8.3 short names exist only on Windows")


def _short(path: Path) -> Path:
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, len(buf))
    return Path(buf.value) if n else path


@pytest.fixture
def short_workspace(tmp_dir: Path) -> Path:
    base = tmp_dir / "a-directory-name-longer-than-eight-characters"
    base.mkdir()
    short = _short(base)
    if short == base:
        pytest.skip("8.3 short names are disabled on this volume")
    return create_run_workspace(short, new_run_id())


def test_file_write_accepts_a_short_path_workspace(short_workspace):
    result = FileWriteTool(short_workspace)(path="generated/test_a.py", content="def test_a():\n    pass\n")
    assert result.data["path"] == "generated/test_a.py"


def test_pytest_tool_accepts_a_short_path_workspace(short_workspace):
    (short_workspace / "generated" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    result = PytestTool(short_workspace, "http://sut.test")(paths=["generated/test_a.py"])
    assert result.ok, result.stdout
    assert result.data["results"] == [{"node_id": "generated/test_a.py::test_a", "outcome": "PASS", "message": ""}]
    assert "l1_denials" not in result.data
