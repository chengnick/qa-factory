"""Prompt version. Any change to an agent prompt must bump this (spec v3 §3.3, §13 Phase 2R).

tests/agents/test_prompt_version.py pins a hash of every prompt to this version, so an edited
prompt without a version bump fails the test suite.
"""

PROMPT_VERSION = "v3"
