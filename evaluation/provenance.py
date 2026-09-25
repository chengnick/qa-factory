"""Fixed conditions recorded with every run and evaluation (spec v3 §11.3)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = REPO_ROOT / "requirements.lock"


def git_commit() -> dict[str, object]:
    """{"sha": ..., "dirty": bool}; sha is None outside a git checkout."""
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}
    return {"sha": sha, "dirty": bool(status.strip())}


def lockfile_sha256(path: Path = LOCKFILE) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
