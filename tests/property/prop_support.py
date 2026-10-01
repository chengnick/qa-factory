"""Shared pieces for the property-based tests: only agents, tools, paths and URLs that exist in the system."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from hypothesis import strategies as st

from observability.instrument import Instrumentation, TracedToolRegistry
from observability.setup import create_tracer_provider, get_tracer
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from permissions.gate import PermissionGate
from permissions.policy import REPO_ROOT, default_policy
from security.events import SecurityRecorder
from testing.fake_clock import FakeClock
from tools.registry import NO_RETRY, ToolRegistry, ToolResult
from tools.workspace import create_run_workspace

WINDOWS = os.name == "nt"
PORT = 8765
SUT = f"http://127.0.0.1:{PORT}"
AGENTS = ("requirement", "test_design", "automation", "qa", "report")  # the pipeline's agents (permissions/policy.py)
TOOLS = ("file_write", "pytest", "http_request", "playwright")  # the registered tools (policy KNOWN_TOOLS)
RUN_ID = "RUN-20991231-235959-AAAA"
OTHER_RUN = "RUN-20990101-000000-BBBB"


class Spy:
    """Stands in for a tool: counts executions, never does anything."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, **_: object) -> ToolResult:
        self.calls += 1
        return ToolResult(ok=True, exit_code=0, stdout="spy", command="spy")


@dataclass
class World:
    workspace: Path
    spies: dict[str, Spy]
    recorder: SecurityRecorder
    gate: PermissionGate
    traced: TracedToolRegistry

    @property
    def executions(self) -> int:
        return sum(s.calls for s in self.spies.values())


@contextmanager
def gated_world() -> Iterator[World]:
    """A run workspace, spy tools behind the real permission gate and the real traced registry."""
    with tempfile.TemporaryDirectory(prefix="qa-prop-") as tmp:
        workspace = create_run_workspace(Path(tmp).resolve() / "artifacts", RUN_ID)
        spies = {t: Spy() for t in TOOLS}
        registry = ToolRegistry()
        for name, spy in spies.items():
            registry.register(name, spy, retry=NO_RETRY)
        recorder = SecurityRecorder(RUN_ID)
        gate = PermissionGate(recorder, registered=registry.names, workspace=workspace, sut_url=SUT, policy=default_policy())
        inst = Instrumentation(get_tracer(create_tracer_provider(InMemorySpanExporter())), FakeClock())
        yield World(workspace, spies, recorder, gate, TracedToolRegistry(registry, inst, guard=gate.check))


# --------------------------------------------------------------------------- URLs

EVIL_HOSTS = st.sampled_from(["evil.test", "attacker.invalid", "example.com"]) | st.from_regex(r"[a-z]{1,8}\.(test|invalid)", fullmatch=True)


@st.composite
def lookalike_hosts(draw) -> str:
    """Hosts that start like the SUT's but are not the SUT."""
    evil = draw(EVIL_HOSTS)
    kind = draw(st.sampled_from(["userinfo", "extra_digit", "subdomain", "prefix_label", "path_trick"]))
    return {
        "userinfo": f"127.0.0.1:{PORT}@{evil}",
        "extra_digit": f"127.0.0.1:{PORT}{draw(st.integers(0, 9))}",
        "subdomain": f"127.0.0.1:{PORT}.{evil}",
        "prefix_label": f"127.0.0.1.{evil}:{PORT}",
        "path_trick": f"{evil}/127.0.0.1:{PORT}",
    }[kind]


@st.composite
def lookalike_urls(draw) -> str:
    scheme = draw(st.sampled_from(["http", "https", "HTTP", "Http"]))
    path = draw(st.sampled_from(["", "/", "/api/tasks", "/api/projects/1/tasks?limit=5"]))
    return f"{scheme}://{draw(lookalike_hosts())}{path}"


@st.composite
def lookalike_routes(draw) -> str:
    """http_request routes that would leave the SUT: absolute URLs and suffixes glued onto the base URL."""
    evil = draw(EVIL_HOSTS)
    return draw(st.sampled_from([
        draw(lookalike_urls()),
        f"//{evil}/api/tasks",
        f"\\\\{evil}\\api",
        f"@{evil}/api/tasks",
        f"{draw(st.integers(0, 9))}/api/tasks",
        f".{evil}/api/tasks",
        f"{SUT}@{evil}/",
    ]))  # fmt: skip


SUT_ROUTES = st.sampled_from(["/health", "/api/tasks/1", "/api/projects", "/api/projects/7/tasks?limit=100", "/api/users"])
