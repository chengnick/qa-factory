"""benchmark.matrix exits non-zero when any cell does not match the expectation (CI depends on it)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from benchmark import matrix
from benchmark.matrix import ConfigResult

REPO = Path(__file__).resolve().parents[2]


def _fake_run_config(broken: str | None):
    def run(name, enabled, workdir):
        bug_ids = matrix.load_bug_ids()
        outcomes = {b: ("FAIL" if b in enabled else "PASS") for b in bug_ids}
        if broken is not None and name == broken:
            outcomes[bug_ids[0]] = "PASS" if outcomes[bug_ids[0]] == "FAIL" else "FAIL"
        return ConfigResult(name, enabled, outcomes, 0.0, "")

    return run


@pytest.mark.parametrize("broken, code", [(None, 0), ("clean", 1), ("B02", 1), ("all", 1)])
def test_exit_code_reflects_mismatches(monkeypatch, tmp_dir, capsys, broken, code):
    monkeypatch.setattr(matrix, "run_config", _fake_run_config(broken))
    assert matrix.main(["--jobs", "1", "--out", str(tmp_dir / "m.md")]) == code
    report = (tmp_dir / "m.md").read_text(encoding="utf-8")
    assert ("→ FAIL" in report) is bool(code) and ("→ PASS" in report) is (not code)


def test_process_exit_code_is_non_zero_on_mismatch(tmp_dir):
    """The module entry point propagates main()'s return value as the process exit code."""
    script = (
        "import sys; from benchmark import matrix; from benchmark.matrix import ConfigResult\n"
        "ids = matrix.load_bug_ids()\n"
        "matrix.run_config = lambda n, e, w: ConfigResult(n, e, {b: 'PASS' for b in ids}, 0.0, '')\n"
        f"sys.exit(matrix.main(['--jobs', '1', '--out', r'{tmp_dir / 'm.md'}']))\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 1, proc.stdout + proc.stderr
