"""L1 guard (spec v3 §8.2, Phase 4): generated test code, run by the pytest tool, cannot write outside its own files,
reach anything but the SUT, start processes or load native libraries. Each probe test below passes only if the
guard refused the action; the files they aim at are checked afterwards from the outside.

The code policy is switched off (enforce_policy=False) so the probes can import os/socket/ctypes: this tests the
L1 layer on its own. The guard is an in-process check, not an OS sandbox (see tools/l1_guard.py).
"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools.pytest_tool import PytestTool
from tools.workspace import create_run_workspace, new_run_id

REPO = Path(__file__).resolve().parents[2]
PROBE = "l1_probe_must_not_exist.txt"


@pytest.fixture
def sut_url() -> Iterator[str]:
    """A tiny HTTP server standing in for the SUT."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture
def workspace(tmp_dir: Path) -> Path:
    return create_run_workspace(tmp_dir, new_run_id())


def _run(workspace: Path, sut_url: str, body: str, isolation: str = "L1"):
    (workspace / "generated" / "test_probe.py").write_text(body, encoding="utf-8")
    return PytestTool(workspace, sut_url, enforce_policy=False, isolation=isolation)(paths=["generated/test_probe.py"])


def _refused(call: str, setup: str = "") -> str:
    return (
        "import os, shutil, socket, subprocess, sys\nimport pytest\n\n"
        "def test_refused():\n"
        f"{setup}"
        "    with pytest.raises(PermissionError, match='L1 guard'):\n"
        f"        {call}\n"
    )


@pytest.fixture
def repo_probes() -> Iterator[list[Path]]:
    targets = [REPO / "sut" / PROBE, REPO / "benchmark" / PROBE]
    yield targets
    for t in targets:  # only if the guard failed; keeps the repo clean for the next run
        if t.exists():
            t.unlink()


# --------------------------------------------------------------------------- acceptance: sut/ and benchmark/


@pytest.mark.parametrize("folder", ["sut", "benchmark"])
def test_generated_code_cannot_write_into_sut_or_benchmark(workspace, sut_url, repo_probes, folder):
    target = REPO / folder / PROBE
    result = _run(workspace, sut_url, _refused(f"open({str(target)!r}, 'w').write('x')"))

    assert result.ok, result.stdout
    assert not target.exists()
    assert [(d["event"], Path(d["target"]).name) for d in result.data["l1_denials"]] == [("open", PROBE)]


def test_without_l1_the_same_write_goes_through(workspace, sut_url, tmp_dir):
    """Control: the L0+ layer alone does not stop file writes (what README says about L0+)."""
    target = tmp_dir / "outside" / PROBE
    target.parent.mkdir()
    body = f"def test_write():\n    open({str(target)!r}, 'w').write('x')\n"
    assert _run(workspace, sut_url, body, isolation="L0+").ok
    assert target.read_text(encoding="utf-8") == "x"


# --------------------------------------------------------------------------- files


@pytest.mark.parametrize(
    "call",
    [
        "open(os.path.join(os.getcwd(), 'meta.json'), 'w')",  # run evidence in its own workspace
        "open(os.path.join(os.getcwd(), 'generated', 'test_probe.py'), 'a')",  # the tests themselves
        "os.open(os.path.join(os.getcwd(), 'x.txt'), os.O_CREAT | os.O_WRONLY)",
        "os.remove(os.path.join(os.getcwd(), 'pytest.ini'))",
        "os.rename(os.path.join(os.getcwd(), 'pytest.ini'), 'moved.ini')",
        "os.mkdir(os.path.join(os.getcwd(), 'newdir'))",
        "shutil.rmtree(os.path.join(os.getcwd(), 'generated'))",
        "os.link(os.path.join(os.getcwd(), 'pytest.ini'), 'hard.ini')",
        "os.symlink(os.path.join(os.getcwd(), 'pytest.ini'), 'soft.ini')",
    ],
    ids=["meta", "own-tests", "os.open", "remove", "rename", "mkdir", "rmtree", "hardlink", "symlink"],
)
def test_workspace_is_read_only_for_generated_code(workspace, sut_url, call):
    (workspace / "generated" / "test_probe.py").write_text(_refused(call), encoding="utf-8")
    before = _snapshot(workspace)
    result = PytestTool(workspace, sut_url, enforce_policy=False)(paths=["generated/test_probe.py"])

    assert result.ok, result.stdout
    assert _snapshot(workspace) == before


def _snapshot(workspace: Path) -> dict[str, bytes]:
    """Every file except what the tool itself adds per call (reports/, tmp/)."""
    files = (p for p in workspace.rglob("*") if p.is_file() and not {"reports", "tmp", "__pycache__"} & set(p.parts))
    return {p.relative_to(workspace).as_posix(): p.read_bytes() for p in files}


def test_reading_the_repo_env_file_is_refused(workspace, sut_url):
    result = _run(workspace, sut_url, _refused(f"open({str(REPO / '.env')!r}).read()"))
    assert result.ok, result.stdout


def test_allowed_writes_still_work(workspace, sut_url):
    body = (
        "import os, tempfile\n\n"
        "def test_temp_is_private_and_writable():\n"
        "    path = os.path.join(tempfile.gettempdir(), 'scratch.txt')\n"
        "    open(path, 'w').write('ok')\n"
        "    assert os.path.commonpath([path, os.getcwd()]) == os.getcwd()\n"
        "    assert open(os.devnull, 'w').write('x') == 1\n"
    )
    result = _run(workspace, sut_url, body)
    assert result.ok, result.stdout
    assert "l1_denials" not in result.data
    assert result.data["isolation"] == "L1"
    assert list((workspace / "tmp").rglob("scratch.txt"))


def test_reading_the_repo_is_allowed(workspace, sut_url):
    body = f"def test_read():\n    assert 'def ' in open({str(REPO / 'sut' / 'app.py')!r}).read()\n"
    assert _run(workspace, sut_url, body).ok


# --------------------------------------------------------------------------- network


def test_sut_is_reachable(workspace, sut_url):
    body = "import httpx\n\ndef test_sut(base_url):\n    assert httpx.get(base_url + '/').text == 'ok'\n"
    result = _run(workspace, sut_url, body)
    assert result.ok, result.stdout


@pytest.mark.parametrize(
    "call",
    [
        "socket.create_connection(('127.0.0.1', 9), timeout=1)",  # another local port
        "socket.getaddrinfo('example.com', 443)",  # DNS for another host
        "socket.socket().bind(('0.0.0.0', 0))",  # a listener on all interfaces
        "socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('8.8.8.8', 53))",
    ],
    ids=["other-port", "dns", "bind-any", "udp"],
)
def test_other_network_targets_are_refused(workspace, sut_url, call):
    result = _run(workspace, sut_url, _refused(call))
    assert result.ok, result.stdout


# --------------------------------------------------------------------------- processes and native code


@pytest.mark.parametrize(
    "call",
    [
        "subprocess.run([sys.executable, '-c', 'print(1)'])",
        "os.system('echo hi')",
        "__import__('ctypes').CDLL('msvcrt' if os.name == 'nt' else 'libc.so.6')",
        "__import__('ctypes').string_at(id(1), 8)",
    ],
    ids=["subprocess", "os.system", "ctypes-load", "ctypes-memory"],
)
def test_processes_and_native_code_are_refused(workspace, sut_url, call):
    result = _run(workspace, sut_url, _refused(call))
    assert result.ok, result.stdout


# --------------------------------------------------------------------------- reporting


def test_refusals_become_security_events(harness, workspace, sut_url, repo_probes):
    """Through the traced registry, each refusal is a PERMISSION_DENIED event (executed: false) on the tool span."""
    from observability.instrument import TracedToolRegistry
    from security.events import SecurityRecorder
    from tools.registry import ToolRegistry
    import dataclasses

    (workspace / "generated" / "test_probe.py").write_text(_refused(f"open({str(repo_probes[0])!r}, 'w')"), encoding="utf-8")
    registry = ToolRegistry()
    registry.register("pytest", PytestTool(workspace, sut_url, enforce_policy=False))
    recorder = SecurityRecorder("RUN-X")
    traced = TracedToolRegistry(registry, dataclasses.replace(harness.inst, security=recorder))

    traced.call_as("qa", "pytest", {"paths": ["generated/test_probe.py"]})

    (event,) = recorder.events
    assert (event.type, event.agent, event.action, event.executed) == ("PERMISSION_DENIED", "qa", "l1:open", False)
    assert event.target.endswith(PROBE)
    span = harness.one("tool.pytest")
    assert span.attributes["qa.isolation.level"] == "L1" and span.attributes["qa.isolation.denials"] == 1


def test_unknown_isolation_level_is_rejected(workspace, sut_url):
    with pytest.raises(ValueError):
        PytestTool(workspace, sut_url, isolation="L9")


# --------------------------------------------------------------------------- process events per Python version


@pytest.mark.parametrize("event", ["subprocess.Popen", "os.posix_spawn", "os.posix_spawnp", "os.exec", "os.spawn"])
def test_process_events_allow_only_the_playwright_driver(tmp_dir, event):
    """Python 3.14 on Linux starts subprocesses with os.posix_spawn after the subprocess.Popen event (CI canary, run #2)."""
    from tools.l1_guard import Guard

    driver = tmp_dir / "driver"
    driver.mkdir()
    node = driver / "node"
    guard = Guard({"write": [], "exec": [str(driver)], "sut_host": "127.0.0.1", "sut_port": 1})

    guard(event, (str(node), [str(node), "cli.js", "run-driver"], {}))  # allowed
    guard(event, (None, [str(node), "cli.js"], {}))  # program taken from argv[0]
    with pytest.raises(PermissionError, match="only the Playwright driver"):
        guard(event, (str(tmp_dir / "sh"), [str(tmp_dir / "sh"), "-c", "id"], {}))
