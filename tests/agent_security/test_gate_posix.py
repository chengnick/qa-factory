"""POSIX absolute paths for the gate (the Windows-only cases live in test_gate.py behind skipif)."""

import os
from pathlib import Path

import pytest

from permissions.gate import PermissionGate
from security.events import SecurityRecorder

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX absolute paths (/etc/...) are not absolute on Windows")


def test_posix_absolute_paths(tmp_dir):
    workspace = tmp_dir / "artifacts" / "RUN-20260927-000000-AAAA"
    gate = PermissionGate(SecurityRecorder(), registered=lambda: ("file_write",), workspace=workspace, repo_root=tmp_dir)
    assert gate.classify_path("/etc/passwd") == "OUTSIDE"
    assert gate.classify_path(str(tmp_dir / "sut" / "app.py")) == "PROTECTED"
    assert gate.classify_path(str(Path(workspace) / "generated" / "test_a.py")) == "OWN_GENERATED"
    assert gate.classify_path("/" + str(tmp_dir / "artifacts").lstrip("/") + "/RUN-X/trace.json") == "EVIDENCE"
