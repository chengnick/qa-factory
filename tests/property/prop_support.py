"""Shared pieces for the property-based tests: only agents, tools, paths and URLs that exist in the system."""

from __future__ import annotations

import contextlib
import html
import json
import os
import string
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from hypothesis import strategies as st

from observability.redact import find_secret
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


# --------------------------------------------------------------------------- secrets

# Synthetic secrets only. Each strategy draws (text as written, value that must not survive): for whole-token
# formats the token itself, for "Bearer x" and "key=x" the part redact() masks. Shapes follow observability/redact.py.
_ALNUM = string.ascii_letters + string.digits
KEY_NAMES = ("api_key", "API-KEY", "apikey", "client_secret", "auth_token", "session.token", "password", "db_passwd", "pwd")


def _value(alphabet: str, lo: int, hi: int) -> st.SearchStrategy[str]:
    # characters via sampled_from: Hypothesis 6.168.3 crashes while shrinking text strategies with different alphabets
    return st.text(st.sampled_from(sorted(set(alphabet))), min_size=lo, max_size=hi)


def _whole(prefix: st.SearchStrategy[str], body: st.SearchStrategy[str]) -> st.SearchStrategy[tuple[str, str]]:
    return st.builds(lambda p, b: (p + b, p + b), prefix, body)


SECRET_FORMATS: dict[str, st.SearchStrategy[tuple[str, str]]] = {
    "sk": _whole(st.sampled_from(["sk-", "sk-ant-"]), _value(_ALNUM + "_-", 16, 40)),
    "aws": _whole(st.just("AKIA"), _value(string.ascii_uppercase + string.digits, 16, 16)),
    "google": _whole(st.just("AIza"), _value(_ALNUM + "_-", 35, 35)),
    "github": _whole(st.sampled_from(["ghp_", "gho_", "ghu_", "ghs_", "ghr_"]), _value(_ALNUM, 20, 40)),
    "bearer": st.builds(lambda v: (f"Bearer {v}", v), _value(_ALNUM + "._~+/-", 12, 40)),
    "key_value": st.builds(
        lambda k, sep, v: (f"{k}{sep}{v}", v),
        st.sampled_from(KEY_NAMES),
        st.sampled_from(["=", ": ", " = ", '": "', "='"]),
        _value(_ALNUM + "-_.~/+@#$%!", 12, 40),
    ),
}
format_secrets = st.one_of([st.tuples(st.just(name), SECRET_FORMATS[name]) for name in sorted(SECRET_FORMATS)])
exact_secrets = _value(_ALNUM, 24, 48)  # an API key value as configured in the environment


def encodings(value: str) -> dict[str, str]:
    """The forms a value can take in a saved file."""
    return {"raw": value, "json": json.dumps(value)[1:-1], "xml": html.escape(value), "url": quote(value, safe="")}


TEXT_SUFFIXES = {".json", ".txt", ".log", ".py", ".ini", ".xml", ".md"}
IMAGE_SUFFIXES = {".png", ".jpeg", ".jpg"}  # raw bytes only (metadata); text drawn into pixels is out of scope
TRACE_JSONL = (".trace", ".network", ".stacks")


def _json_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _json_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _json_strings(v)


def _text_views(name: str, data: bytes) -> Iterator[str]:
    """The raw text plus decoded views: JSON strings (escapes undone) and XML text / attributes."""
    text = data.decode("utf-8", errors="replace")
    yield text
    if name.endswith(".json"):
        with contextlib.suppress(ValueError):
            yield "\n".join(_json_strings(json.loads(text)))
    if name.endswith(TRACE_JSONL):
        for line in text.splitlines():
            with contextlib.suppress(ValueError):
                yield "\n".join(_json_strings(json.loads(line)))
    if name.endswith(".xml"):
        with contextlib.suppress(ElementTree.ParseError):
            for el in ElementTree.fromstring(data).iter():
                yield "\n".join([el.text or "", el.tail or "", *el.attrib.values()])


# Files stored byte-exact, because they are evidence (rounds.json hashes the tests, W05 checks the Playwright
# evidence): they cannot be masked. The guarantee for them is narrower (owner decision, 2026-10-06): no string the
# gate's secret scan detects (redact.SECRET_SHAPES), since a test containing one is never written. A secret that
# redact() masks but SECRET_SHAPES does not detect (e.g. a short Bearer value, auth_token=...) can stay in them.
VERBATIM_EVIDENCE = ("generated/", "reports/junit-", "playwright/")


@dataclass
class Scan:
    hits: list[tuple[str, str]]  # (file or file[member], form)
    unscanned: list[str]  # files of a type the scan does not know: a new artifact type must not slip through
    files: int
    shaped: set[str]  # files (or members) holding a string SECRET_SHAPES detects

    def leaks(self) -> list[str]:
        """Hits that break the guarantee: anywhere outside verbatim evidence, or a detected shape inside it."""
        return [f"{where}: {form}" for where, form in self.hits if not where.startswith(VERBATIM_EVIDENCE) or where in self.shaped]


def _search(where: str, data: bytes, name: str, forms: dict[str, str], scan: Scan, text: bool) -> None:
    views = list(_text_views(name, data)) if text else []
    if text and find_secret(views[0]):
        scan.shaped.add(where)
    for form, needle in forms.items():
        if needle.encode("utf-8") in data or any(needle in v for v in views):
            scan.hits.append((where, form))


def scan_saved_files(workspace: Path, values: list[str]) -> Scan:
    """Every file under the run directory, trace.zip members included, searched for every encoding of every value."""
    forms = {f"{i}/{form}": needle for i, v in enumerate(values) for form, needle in encodings(v).items()}
    scan = Scan([], [], 0, set())
    for path in sorted(p for p in workspace.rglob("*") if p.is_file()):
        rel, suffix, data = path.relative_to(workspace).as_posix(), path.suffix.lower(), path.read_bytes()
        scan.files += 1
        if suffix in TEXT_SUFFIXES:
            _search(rel, data, rel, forms, scan, text=True)
        elif suffix == ".zip":
            with zipfile.ZipFile(path) as zf:
                for member in zf.namelist():
                    _search(f"{rel}[{member}]", zf.read(member), member, forms, scan,
                            text=not member.lower().endswith(tuple(IMAGE_SUFFIXES)))  # fmt: skip
        elif suffix in IMAGE_SUFFIXES:
            _search(rel, data, rel, forms, scan, text=False)
        else:
            scan.unscanned.append(rel)
    return scan
