"""Per-run workspace: the only directory generated tests are written to and executed in.

    artifacts/{run_id}/            run_id = RUN-YYYYMMDD-HHMMSS-XXXX (spec v3 §4.1)
        generated/conftest.py   copy of the owner-written fixtures (read-only for agents)
        generated/test_*.py     written by the Automation agent via file_write
        generated/roundN/       read-only snapshot of the tests of round N (spec v3 §4.2), taken by the pipeline
        pytest.ini              stops pytest from picking up the repo's pyproject (and its pythonpath)

Workspaces are never deleted automatically.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import stat
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_CONFTEST = REPO_ROOT / "generated" / "conftest.py"
PYTEST_INI = "[pytest]\n# Isolated run workspace: no repo config, no repo on sys.path.\n"


RUN_ID_PATTERN = re.compile(r"^RUN-\d{8}-\d{6}-[0-9A-F]{4}$")


def new_run_id() -> str:
    """Human-facing run id (UTC timestamp + 4 random hex); maps 1:1 to an OTel trace_id via meta.json."""
    return f"RUN-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def ensure_pytest_ini(workspace: Path) -> Path:
    ini = workspace / "pytest.ini"
    if not ini.exists():
        ini.write_text(PYTEST_INI, encoding="utf-8")
    return ini


def create_run_workspace(base: Path, run_id: str) -> Path:
    workspace = base / run_id
    if workspace.exists():
        raise FileExistsError(f"run workspace already exists: {workspace}")
    (workspace / "generated").mkdir(parents=True)
    shutil.copyfile(OWNER_CONFTEST, workspace / "generated" / "conftest.py")
    ensure_pytest_ini(workspace)
    return workspace


def snapshot_round(workspace: Path, round_no: int, files: Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    """Save (path, content) pairs as generated/round{N}/{name}, read-only. Returns path, snapshot and sha256 per file.

    Rounds never overwrite each other; a snapshot that already exists is an error.
    """
    folder = workspace / "generated" / f"round{round_no}"
    folder.mkdir(parents=True, exist_ok=False)
    saved = []
    for path, content in files:
        target = folder / Path(path).name
        target.write_text(content, encoding="utf-8", newline="")
        os.chmod(target, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        saved.append({"path": path, "snapshot": target.relative_to(workspace).as_posix(), "sha256": digest})
    return saved
