"""Fixed conditions recorded with every run and evaluation (spec v3 §11.3)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = REPO_ROOT / "requirements.lock"


def git_commit(repo: Path = REPO_ROOT) -> dict[str, object]:
    """{"sha": ..., "dirty": bool}; sha is None outside a git checkout.

    dirty = a *tracked* file differs from HEAD (staged or not). Untracked files never count: the evaluation
    runner itself adds untracked result directories while it runs (Phase 2R: 29/30 runs wrongly marked dirty).
    """
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}
    return {"sha": sha, "dirty": bool(status.strip())}


def lockfile_sha256(path: Path = LOCKFILE) -> str | None:
    """sha256 of the lockfile with line endings normalised to LF, like the policy and conftest hashes, so a CRLF
    checkout (Windows, core.autocrlf) and an LF one hash the same content identically. Before amendment A8 the raw
    bytes were hashed: runs up to then recorded the CRLF value of this machine's checkout."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


OWNER_CONFTEST = REPO_ROOT / "generated" / "conftest.py"


def conftest_sha256(path: Path = OWNER_CONFTEST) -> str | None:
    """The owner-written fixtures change what generated tests can do (Phase 4: Playwright evidence) without a
    prompt change, so their hash is recorded next to the prompt version. Line endings normalised to LF."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
