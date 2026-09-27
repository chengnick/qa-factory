"""Write a modified copy of the default policy to a temp file and load it."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from permissions.policy import DEFAULT_POLICY_PATH, Policy, load_policy


def default_raw() -> dict[str, Any]:
    return yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))


def write_policy(tmp_dir: Path, raw: dict[str, Any] | str, name: str = "policy.yaml") -> Path:
    path = tmp_dir / name
    path.write_text(raw if isinstance(raw, str) else yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def modified(tmp_dir: Path, change: Callable[[dict[str, Any]], None]) -> Policy:
    raw = copy.deepcopy(default_raw())
    change(raw)
    return load_policy(write_policy(tmp_dir, raw))
