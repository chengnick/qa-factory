"""git_commit(): dirty means a tracked file changed; untracked files (e.g. new result directories) never count."""

import subprocess
from pathlib import Path

import pytest

from evaluation.provenance import git_commit, lockfile_sha256


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_dir: Path) -> Path:
    _git(tmp_dir, "init", "-q")
    (tmp_dir / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_dir, "add", "code.py")
    _git(tmp_dir, "commit", "-q", "-m", "init")
    return tmp_dir


def test_clean_checkout(repo):
    commit = git_commit(repo)
    assert commit["dirty"] is False and len(commit["sha"]) == 40


def test_untracked_files_do_not_make_it_dirty(repo):
    results = repo / "benchmark" / "results" / "phase2r" / "RUN-20260925-160546-73BF"
    results.mkdir(parents=True)
    (results / "meta.json").write_text("{}", encoding="utf-8")
    (repo / "scratch.txt").write_text("x", encoding="utf-8")

    assert git_commit(repo)["dirty"] is False


def test_modified_tracked_file_is_dirty(repo):
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    assert git_commit(repo)["dirty"] is True


def test_staged_change_is_dirty(repo):
    (repo / "new.py").write_text("y = 1\n", encoding="utf-8")
    _git(repo, "add", "new.py")
    assert git_commit(repo)["dirty"] is True


def test_outside_a_checkout(tmp_dir):
    assert git_commit(tmp_dir / "missing") == {"sha": None, "dirty": None}


def test_lockfile_hash(tmp_dir):
    lock = tmp_dir / "requirements.lock"
    assert lockfile_sha256(lock) is None
    lock.write_text("a==1\n", encoding="utf-8")
    assert len(lockfile_sha256(lock)) == 64


def test_lockfile_hash_ignores_line_endings(tmp_dir):
    """A CRLF checkout (Windows, core.autocrlf=true) and an LF checkout of the same lockfile hash the same (amendment A8)."""
    lf, crlf = tmp_dir / "lf.lock", tmp_dir / "crlf.lock"
    lf.write_bytes(b"a==1\nb==2\n")
    crlf.write_bytes(b"a==1\r\nb==2\r\n")
    assert lockfile_sha256(lf) == lockfile_sha256(crlf)
