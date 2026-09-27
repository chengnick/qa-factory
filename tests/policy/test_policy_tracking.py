"""Policy hash (LF-normalised) and permission-check events and statistics (spec v3.1 §8.5.4)."""

from __future__ import annotations

import json

from agents.contracts import QAResult
from permissions.policy import DEFAULT_POLICY_PATH, load_policy, policy_hash
from testing.fake_agent import ToolCall, scripted
from tests.policy.support import write_policy


def test_crlf_and_lf_hash_the_same(tmp_dir):
    text = DEFAULT_POLICY_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    lf = tmp_dir / "lf.yaml"
    crlf = tmp_dir / "crlf.yaml"
    lf.write_bytes(text.encode("utf-8"))
    crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert lf.read_bytes() != crlf.read_bytes()
    assert load_policy(lf).hash == load_policy(crlf).hash == load_policy().hash == policy_hash(text)


def test_hash_changes_with_content(tmp_dir):
    text = DEFAULT_POLICY_PATH.read_text(encoding="utf-8")
    changed = write_policy(tmp_dir, text.replace('"sut/"', '"sut/"  # comment'))
    assert load_policy(changed).hash != load_policy().hash


def test_hash_and_stats_recorded_on_root_span_and_meta(run_scenario):
    s = run_scenario()
    root = s.spans("qa.run")[0]
    assert root.attributes["qa.policy.hash"] == load_policy().hash
    assert root.attributes["qa.policy.path"] == "config/agent_policy.yaml"
    assert s.result.policy["hash"] == load_policy().hash


def _check_events(s):
    return [e for span in s.spans() for e in span.events if e.name == "qa.permission.check"]


def test_every_check_is_an_event_and_counts_match(run_scenario):
    calls = [
        ToolCall("file_write", {"path": "generated/test_a.py", "content": "x = 1\n"}, swallow=True),  # QA: deny
        ToolCall("http_request", {"method": "GET", "route": "/health"}, swallow=True),  # allow
        ToolCall("http_request", {"method": "GET", "route": "https://evil.test/"}, swallow=True),  # deny
        ToolCall("shell", {}, swallow=True),  # unregistered: deny
    ]
    s = run_scenario(agents={"qa": scripted("qa", calls, lambda automation: QAResult("REQ-005", ()))})
    events = _check_events(s)
    stats = s.result.policy
    assert stats["permission_checks"] == len(events) == stats["allowed"] + stats["denied"]
    assert stats["allowed"] == sum(e.attributes["decision"] == "allow" for e in events)
    assert stats["denied"] == sum(e.attributes["decision"] == "deny" for e in events) >= 3
    matched = {e.attributes["matched"] for e in events}
    assert {"agents.qa.tools", "agents.qa.tools.http_request.url_allowlist", "registry"} <= matched
    write = next(e for e in events if e.attributes["tool"] == "file_write" and e.attributes["decision"] == "allow")
    assert write.attributes["agent"] == "automation"
    assert write.attributes["matched"] == "agents.automation.tools.file_write.path_prefix"


def test_meta_carries_policy_hash_and_stats_but_security_events_do_not(tmp_dir):
    import app

    assert app.main(["--requirement", "REQ-005", "--llm", "fake", "--artifacts-dir", str(tmp_dir)]) == 0
    (run_dir,) = [p for p in tmp_dir.iterdir() if p.is_dir()]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    security = json.loads((run_dir / "security_events.json").read_text(encoding="utf-8"))
    trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
    events = [e for sp in trace["spans"] for e in sp["events"] if e["name"] == "qa.permission.check"]
    assert meta["policy_hash"] == load_policy().hash and meta["policy_path"] == "config/agent_policy.yaml"
    assert meta["permission_checks"]["permission_checks"] == len(events) > 0
    assert set(security) == {"run_id", "breach", "events"}  # only security events live there
