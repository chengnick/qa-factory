"""Deterministic fault-injection harness: fake LLM/provider/tools, a real gate and FileWriteTool in a temp workspace.

No SUT, no network, no real LLM; time is a FakeClock (retry backoff costs nothing).
"""

from tests.agent_faults.support import run_scenario  # noqa: F401  (fixture)
