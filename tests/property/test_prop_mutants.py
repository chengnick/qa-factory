"""Do the properties catch real mistakes? Each test injects one bug with monkeypatch (no production code is edited),
runs the property that should notice it, and requires the property to fail. The shrunk counterexample Hypothesis
reports is printed (run with -s to see it)."""

from __future__ import annotations

import ast

import pytest

import classification.verdict as verdict_mod
import evaluation.workflow as workflow
import permissions.gate as gate_mod
from observability.instrument import TracedToolRegistry
from permissions.policy import Policy
from tests.property import test_prop_gate as gate_props
from tests.property import test_prop_paths as path_props
from tests.property import test_prop_urls as url_props
from tests.property import test_prop_verdict as verdict_props
from tests.property import test_prop_w01 as w01_props
from tests.property.prop_support import WINDOWS
from tools.registry import PermissionDeniedError, UnknownToolError


def _caught(prop) -> str:
    """Run a property that must fail; return Hypothesis's minimal counterexample."""
    with pytest.raises(BaseException) as info:  # AssertionError, or the refusal the property expected not to see
        prop()
    if isinstance(info.value, (KeyboardInterrupt, SystemExit)):
        raise info.value
    example = "\n".join(n for n in getattr(info.value, "__notes__", []) if "Falsifying" in n or "data=" in n or "Draw" in n)
    print(f"\n[{prop.__name__}] caught: {type(info.value).__name__}: {str(info.value)[:200]}\n{example}")
    return example


@pytest.mark.skipif(not WINDOWS, reason="normcase only changes anything where paths are case-insensitive")
def test_m1_gate_without_normcase(monkeypatch):
    monkeypatch.setattr(gate_mod, "_norm", lambda path: str(path.resolve()))
    _caught(path_props.test_windows_case_and_backslash_spellings_too)


def test_m2_route_allowlist_as_a_plain_prefix(monkeypatch):
    def weak_check_route(self, agent, route):  # no route-shape check, prefix without the "/" boundary
        base = (self.sut_url or gate_mod.UNBOUND_SUT_URL).rstrip("/")
        key = f"agents.{agent}.tools.http_request.url_allowlist"
        allow = [Policy.expand(u, sut_base_url=base) for u in self.policy.tool_rule(agent, "http_request").url_allowlist]
        if not any((base + route).startswith(prefix) for prefix in allow):
            self._deny("PERMISSION_DENIED", agent, "http_request", route, key, "not allowed")
        self._allow(agent, "http_request", route, key)

    monkeypatch.setattr(gate_mod.PermissionGate, "_check_route", weak_check_route)
    _caught(url_props.test_http_request_refuses_lookalike_routes)


def test_m3_verdict_priority_swapped(monkeypatch):
    original = verdict_mod.aggregate

    def swapped(classifications, *, flaky, missed_possible, flaky_evidence=()):
        sut = next((c for c in classifications if c.layer == "SUT"), None)
        if sut is not None:  # DEFECT_FOUND now wins over AGENT_FAILED
            return verdict_mod.Outcome("DEFECT_FOUND", None, sut, list(classifications), flaky, list(flaky_evidence))
        return original(classifications, flaky=flaky, missed_possible=missed_possible, flaky_evidence=flaky_evidence)

    monkeypatch.setattr(verdict_mod, "aggregate", swapped)
    _caught(verdict_props.test_the_highest_priority_verdict_present_wins)


def test_m4_tool_runs_before_the_gate(monkeypatch):
    original = TracedToolRegistry.call_as

    def execute_first(self, agent, name, args, precheck=None):
        try:
            self._registry.get(name).fn(**dict(args))
        except (UnknownToolError, PermissionDeniedError, TypeError):
            pass
        return original(self, agent, name, args, precheck)

    monkeypatch.setattr(TracedToolRegistry, "call_as", execute_first)
    _caught(gate_props.test_a_refused_call_never_executes_and_records_only_unexecuted_events)


def test_m5_w01_counts_only_plain_asserts(monkeypatch):
    monkeypatch.setattr(workflow, "assertion_count", lambda fn: sum(isinstance(n, ast.Assert) for n in ast.walk(fn)))
    _caught(w01_props.test_removing_assertions_from_a_failing_test_that_then_passes_triggers_w01)
