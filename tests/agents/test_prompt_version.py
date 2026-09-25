"""Prompts are pinned to PROMPT_VERSION: editing a prompt without bumping the version fails here."""

import hashlib

from agents import automation, requirement, test_design
from agents.version import PROMPT_VERSION

# sha256 over the three LLM-facing system prompts, per prompt version.
PROMPT_HASHES = {
    "v3": "7b8edba0f976b7cbf9a9dc2af30c693c910319a67e518575499855def42e82b0",  # used for Phase 2 runs 15-26 and Phase 2R
}


def _prompt_hash() -> str:
    return hashlib.sha256("\n\x00\n".join([requirement.SYSTEM, test_design.SYSTEM, automation.SYSTEM]).encode()).hexdigest()


def test_prompts_match_their_version():
    assert PROMPT_VERSION in PROMPT_HASHES, f"record the hash for new prompt version {PROMPT_VERSION}"
    assert _prompt_hash() == PROMPT_HASHES[PROMPT_VERSION], "prompt changed without bumping agents/version.py"
