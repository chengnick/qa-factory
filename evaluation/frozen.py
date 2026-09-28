"""benchmark/frozen.yaml (spec v3 §3.3, Phase 5): the conditions the held-out test set is run under.

    python -m evaluation.frozen write --model gemini-3.5-flash-lite     # once; this unseals the test set
    python -m evaluation.frozen check --model gemini-3.5-flash-lite     # compare the current checkout

Writing it is the moment the test set is unsealed. Afterwards every test-set run must match it field by field;
the runner refuses otherwise (a changed prompt would make test-set results "contaminated", so they are not
produced at all). The file is written once and never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agents import automation, requirement, test_design
from agents.version import PROMPT_VERSION
from benchmark.datasets import DEV_COMBINATIONS, DEV_REQUIREMENTS, TEST_CLEAN_REQUIREMENTS, TEST_COMBINATIONS
from evaluation.provenance import conftest_sha256, git_commit, lockfile_sha256
from permissions.policy import Policy, default_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN = REPO_ROOT / "benchmark" / "frozen.yaml"
TEMPERATURE = 0.0  # the Gemini adapter's fixed temperature
ROUNDS = 5
# Fields a test-set run must match exactly.
CHECKED = ("prompt_version", "prompt_sha256", "model", "temperature", "lockfile_sha256", "policy_hash", "conftest_sha256",
           "isolation", "max_rounds")  # fmt: skip


def prompt_sha256() -> str:
    """Same hash tests/agents/test_prompt_version.py pins to the prompt version."""
    return hashlib.sha256("\n\x00\n".join([requirement.SYSTEM, test_design.SYSTEM, automation.SYSTEM]).encode()).hexdigest()


def _isolation() -> str:
    from tools.pytest_tool import PytestTool

    return inspect.signature(PytestTool).parameters["isolation"].default


def _max_rounds() -> int:
    from pipeline import run_pipeline

    return inspect.signature(run_pipeline).parameters["max_rounds"].default


def current_conditions(model: str, policy: Policy | None = None) -> dict[str, Any]:
    policy = policy or default_policy()
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": prompt_sha256(),
        "model": model,
        "temperature": TEMPERATURE,
        "lockfile_sha256": lockfile_sha256(),
        "policy_hash": policy.hash,
        "conftest_sha256": conftest_sha256(),
        "isolation": _isolation(),
        "max_rounds": _max_rounds(),
    }


def frozen_document(model: str, policy: Policy | None = None) -> dict[str, Any]:
    commit = git_commit()
    return {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frozen_commit": commit["sha"],
        **current_conditions(model, policy),
        "rounds": ROUNDS,
        "combinations": {
            "dev": [[req, [bug]] for req, bug in DEV_COMBINATIONS] + [[req, []] for req in DEV_REQUIREMENTS],
            "test": [[req, [bug]] for req, bug in TEST_COMBINATIONS] + [[req, []] for req in TEST_CLEAN_REQUIREMENTS],
        },
    }


def load(path: Path = FROZEN) -> dict[str, Any] | None:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def mismatches(frozen: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [f"{k}: frozen {frozen.get(k)!r}, now {current.get(k)!r}" for k in CHECKED if frozen.get(k) != current.get(k)]


def file_sha256(path: Path = FROZEN) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write(model: str, path: Path = FROZEN, policy: Policy | None = None) -> dict[str, Any]:
    if path.exists():
        raise FileExistsError(f"{path} already exists: the test set is frozen once and never re-frozen")
    doc = frozen_document(model, policy)
    header = "# Phase 5 freeze (spec v3 §3.3). Written once by `python -m evaluation.frozen write`; never edited.\n"
    path.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["write", "check"])
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)
    if args.action == "write":
        commit = git_commit()
        if commit["sha"] is None or commit["dirty"]:
            print("refused: the freeze must map to a clean commit", file=sys.stderr)
            return 2
        try:
            doc = write(args.model, FROZEN)
        except FileExistsError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {FROZEN} at commit {doc['frozen_commit']}")
        return 0
    frozen = load(FROZEN)
    if frozen is None:
        print(f"{FROZEN} does not exist: the test set is sealed", file=sys.stderr)
        return 1
    problems = mismatches(frozen, current_conditions(args.model))
    for p in problems:
        print(f"MISMATCH {p}")
    print("matches the freeze" if not problems else f"{len(problems)} mismatch(es)")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
