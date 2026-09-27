"""Instrumentation mounted *around* agents, the LLM client and the tool registry.

Agents never touch OpenTelemetry. The pipeline wraps them:

    llm   = TracedLLM(raw_llm, inst)              -> llm.chat spans
    tools = TracedToolRegistry(registry, inst)    -> tool.<name> spans (+ attempt spans via with_retry)
    agent = traced_agent(RequirementAgent(deps), inst)   -> agent.<name> span
    with traced_run(inst, "REQ-005", sut_bugs) as run: ...   -> qa.run root span

Every timestamp comes from the injected Clock, so FakeClock makes durations exact.
Every retry goes through with_retry(), which emits one `attempt` child span per try.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar

from opentelemetry import context as otel_context
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from llm.client import (
    ChatResponse,
    LLMClient,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    Message,
)
from observability.clock import Clock
from observability.redact import redact
from tools.registry import (
    NO_RETRY,
    RetryPolicy,
    ToolArgumentError,
    ToolRegistry,
    ToolResult,
    ToolTimeoutError,
    UnknownToolError,
)

T = TypeVar("T")
In = TypeVar("In")
Out = TypeVar("Out")

TRUNCATE_CHARS = 2000


# --------------------------------------------------------------------------- content sinks


class ContentSink(Protocol):
    """Stores full (already redacted) large content; returns a reference or None."""

    def store(self, trace_id: str, span_id: str, kind: str, text: str) -> str | None: ...


class NullContentSink:
    def store(self, trace_id: str, span_id: str, kind: str, text: str) -> str | None:
        return None


@dataclass
class MemoryContentSink:
    items: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def store(self, trace_id: str, span_id: str, kind: str, text: str) -> str | None:
        self.items[(trace_id, span_id, kind)] = text
        return f"memory://{trace_id}/{span_id}-{kind}"


class RunContentSink:
    """Per-run layout (spec v3 §4.2): LLM prompts/completions -> prompts/, other large content -> spans/."""

    PROMPT_KINDS = frozenset({"prompt", "completion"})

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)

    def store(self, trace_id: str, span_id: str, kind: str, text: str) -> str | None:
        folder = "prompts" if kind in self.PROMPT_KINDS else "spans"
        path = self.run_dir / folder / f"{span_id}-{kind}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path.relative_to(self.run_dir).as_posix()


class FileContentSink:
    """traces/{trace_id}/artifacts/{span_id}-{kind}.txt"""

    def __init__(self, traces_dir: str | Path) -> None:
        self.traces_dir = Path(traces_dir)

    def store(self, trace_id: str, span_id: str, kind: str, text: str) -> str | None:
        path = self.traces_dir / trace_id / "artifacts" / f"{span_id}-{kind}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path.relative_to(self.traces_dir).as_posix()


# --------------------------------------------------------------------------- core helpers


@dataclass(frozen=True)
class Instrumentation:
    tracer: Tracer
    clock: Clock
    sink: ContentSink = field(default_factory=NullContentSink)
    collector: Any = None  # observability.setup.SpanCollector: lets the pipeline classify its own trace before it ends
    security: Any = None  # security.events.SecurityRecorder for the current run (secret scans before redaction)


def _scan_secret(inst: Instrumentation, action: str, target: str, text: str) -> None:
    """SECRET_ACCESS: scanned on the raw text, *before* record_content redacts it. The stored copy is masked,
    so the secret never reaches an artifact: executed is false."""
    if inst.security is None or not text:
        return
    from observability.redact import find_secret

    if secret := find_secret(text):
        inst.security.record("SECRET_ACCESS", agent=None, action=action, target=target, executed=False,
                             evidence=f"credential-shaped string in {action} (masked in artifacts): {secret}")  # fmt: skip


def _ids(span: Span) -> tuple[str, str]:
    ctx = span.get_span_context()
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def symptom_of(exc: BaseException) -> str | None:
    """Minimal exception -> symptom mapping. The full rule-based classifier arrives in Phase 3."""
    if isinstance(exc, (ToolTimeoutError, LLMTimeoutError, TimeoutError)):
        return "TIMEOUT"
    if isinstance(exc, LLMRateLimitError):
        return "RATE_LIMIT"
    if isinstance(exc, LLMUnavailableError):
        return "HTTP_5XX"
    if isinstance(exc, UnknownToolError):
        return "INVALID_OUTPUT"
    if isinstance(exc, ToolArgumentError):
        return "SCHEMA_MISMATCH"
    if isinstance(exc, ConnectionError):
        return "CONNECTION"
    return None


# Provider-side LLM failures (spec v3 §5.4 R2-R4): layer PROVIDER, verdict ENV_BLOCKED.
# The full rule table (R1-R16) and its evidence output arrive with classification/ in Phase 3.
PROVIDER_RULES: tuple[tuple[type[BaseException], str], ...] = (
    (LLMRateLimitError, "R2"),
    (LLMUnavailableError, "R3"),
    (LLMTimeoutError, "R4"),
    (LLMConnectionError, "R4"),
)


def provider_rule(exc: BaseException) -> str | None:
    for exc_type, rule in PROVIDER_RULES:
        if isinstance(exc, exc_type):
            return rule
    return None


def mark_error(inst: Instrumentation, span: Span, exc: BaseException) -> None:
    message = redact(f"{type(exc).__name__}: {exc}")
    span.set_status(Status(StatusCode.ERROR, message))
    event: dict[str, Any] = {"exception.type": type(exc).__name__, "exception.message": redact(str(exc))}
    if upstream := getattr(exc, "upstream", None):
        event["exception.upstream"] = upstream
    span.add_event("exception", event, timestamp=inst.clock.now_ns())
    if symptom := symptom_of(exc):
        span.set_attribute("qa.failure.symptom", symptom)
    if rule := provider_rule(exc):
        span.set_attribute("qa.failure.layer", "PROVIDER")
        span.set_attribute("qa.failure.rule", rule)


@contextmanager
def start_span(inst: Instrumentation, name: str, attributes: Mapping[str, Any] | None = None, *, root: bool = False) -> Iterator[Span]:
    """Current span with clock-driven timestamps. Exceptions mark it ERROR; otherwise it ends OK unless set."""
    parent_ctx = otel_context.Context() if root else None
    with inst.tracer.start_as_current_span(
        name,
        context=parent_ctx,
        attributes=dict(attributes or {}),
        start_time=inst.clock.now_ns(),
        end_on_exit=False,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException as exc:
            mark_error(inst, span, exc)
            raise
        else:
            if span.status.status_code is StatusCode.UNSET:
                span.set_status(Status(StatusCode.OK))
        finally:
            span.end(end_time=inst.clock.now_ns())


def record_content(inst: Instrumentation, span: Span, kind: str, text: str, *, tail: bool = False) -> None:
    """Large content goes into a truncated span event; the full text goes to the sink. Both redacted."""
    if not text:
        return
    clean = redact(text)
    truncated = len(clean) > TRUNCATE_CHARS
    shown = (clean[-TRUNCATE_CHARS:] if tail else clean[:TRUNCATE_CHARS]) if truncated else clean
    attrs: dict[str, Any] = {"text": shown, "length": len(clean), "truncated": truncated}
    trace_id, span_id = _ids(span)
    if ref := inst.sink.store(trace_id, span_id, kind, clean):
        attrs["artifact"] = ref
    span.add_event(f"{kind}.tail" if tail else kind, attrs, timestamp=inst.clock.now_ns())


def _to_text(value: Any) -> str:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


# --------------------------------------------------------------------------- retry


@dataclass(frozen=True)
class RetryOutcome(Generic[T]):
    value: T
    attempts: int


def with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy,
    inst: Instrumentation,
    *,
    failure_of: Callable[[T], str | None] = lambda _: None,
) -> RetryOutcome[T]:
    """The only sanctioned retry loop. Each try is an `attempt` child span with qa.retry.attempt = 1..n.

    Retries only on policy.retry_on exceptions, at most policy.max_attempts times. A returned result
    that `failure_of` reports as failed marks its attempt ERROR but is final (not retried).
    On final failure the exception gets an `attempts` attribute and is re-raised.
    """
    for attempt in range(1, policy.max_attempts + 1):
        try:
            with start_span(inst, "attempt", {"qa.retry.attempt": attempt}) as span:
                result = fn()
                if message := failure_of(result):
                    span.set_status(Status(StatusCode.ERROR, redact(message)))
            return RetryOutcome(result, attempt)
        except policy.retry_on as exc:
            if attempt == policy.max_attempts:
                _tag_attempts(exc, attempt)
                raise
            if policy.backoff_s > 0:
                inst.clock.sleep(policy.backoff_s * 2 ** (attempt - 1))
        except BaseException as exc:
            _tag_attempts(exc, attempt)
            raise
    raise AssertionError("unreachable")  # pragma: no cover


def _tag_attempts(exc: BaseException, attempts: int) -> None:
    try:
        exc.attempts = attempts  # type: ignore[attr-defined]
    except AttributeError:
        pass


# --------------------------------------------------------------------------- wrappers


class TracedLLM:
    """LLMClient decorator: one llm.chat span per call (GenAI semantic conventions)."""

    def __init__(self, llm: LLMClient, inst: Instrumentation, retry: RetryPolicy = NO_RETRY) -> None:
        self._llm, self._inst, self._retry = llm, inst, retry
        self.model = llm.model

    def chat(self, messages: Sequence[Message]) -> ChatResponse:
        attrs: dict[str, Any] = {"gen_ai.operation.name": "chat", "gen_ai.request.model": self.model}
        temperature = getattr(self._llm, "temperature", None)
        if temperature is not None:
            attrs["gen_ai.request.temperature"] = temperature
        with start_span(self._inst, "llm.chat", attrs) as span:
            record_content(self._inst, span, "prompt", "\n\n".join(f"[{m.role}]\n{m.content}" for m in messages))
            call = lambda: self._llm.chat(messages)  # noqa: E731
            response = with_retry(call, self._retry, self._inst).value if self._retry.max_attempts > 1 else call()
            span.set_attribute("gen_ai.response.model", response.model)
            if response.input_tokens is not None:
                span.set_attribute("gen_ai.usage.input_tokens", response.input_tokens)
            if response.output_tokens is not None:
                span.set_attribute("gen_ai.usage.output_tokens", response.output_tokens)
            _scan_secret(self._inst, "llm.completion", self.model, response.content)
            record_content(self._inst, span, "completion", response.content)
            return response


def _tool_failure(result: ToolResult) -> str | None:
    if result.ok:
        return None
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else f"exit code {result.exit_code}"


Guard = Callable[[str, str, Mapping[str, Any]], None]  # (agent, tool, args) -> raises to refuse


class TracedToolRegistry:
    """Tool calls as tool.<name> spans; tools whose policy allows >1 attempt run through with_retry().

    A guard (the permission gate) runs inside the tool span before anything executes, so a refusal is
    traced like any other tool failure. Calls without an agent (evaluation builds) are not gated.
    """

    def __init__(self, registry: ToolRegistry, inst: Instrumentation, guard: Guard | None = None) -> None:
        self._registry, self._inst, self._guard = registry, inst, guard
        self.round: int | None = None  # set by the pipeline: every tool span of that round gets qa.test.round

    def names(self) -> list[str]:
        return self._registry.names()

    def call(self, name: str, **args: Any) -> ToolResult:
        return self.call_as(None, name, args)

    def call_as(self, agent: str | None, name: str, args: Mapping[str, Any], precheck: Callable[[], None] | None = None) -> ToolResult:
        args = dict(args)
        attrs: dict[str, Any] = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name, "qa.tool.name": name}
        if agent is not None:
            attrs["qa.agent.name"] = agent
        if self.round is not None:
            attrs["qa.test.round"] = self.round
        # Recorded before the call so a tool that raises (e.g. SUT down) still says what it targeted.
        for key in ("method", "route"):
            if isinstance(args.get(key), str):
                attrs[f"qa.http.{key}"] = args[key].upper() if key == "method" else args[key]
        with start_span(self._inst, f"tool.{name}", attrs) as span:
            if precheck is not None:
                precheck()
            if self._guard is not None and agent is not None:
                self._guard(agent, name, args)
            tool = self._registry.get(name)
            tool.validate(args)  # a schema violation never reaches the tool
            invoke = lambda: tool.fn(**args)  # noqa: E731
            if tool.retry.max_attempts > 1:
                outcome = with_retry(invoke, tool.retry, self._inst, failure_of=_tool_failure)
                result, attempts = outcome.value, outcome.attempts
            else:
                result, attempts = invoke(), 1
            self._annotate(span, result)
            self._record_l1_denials(agent, name, result)
            return dataclasses.replace(result, attempts=attempts)

    L1_EVENT_LIMIT = 20

    def _record_l1_denials(self, agent: str | None, tool: str, result: ToolResult) -> None:
        """What the L1 guard refused inside the test subprocess becomes PERMISSION_DENIED events (never executed)."""
        denials = result.data.get("l1_denials") or []
        if self._inst.security is None:
            return
        for d in denials[: self.L1_EVENT_LIMIT]:
            self._inst.security.record("PERMISSION_DENIED", agent=agent, action=f"l1:{d['event']}", target=d["target"], executed=False,
                                       evidence=f"{tool}: generated test code: {d['reason']}")  # fmt: skip

    def _annotate(self, span: Span, result: ToolResult) -> None:
        if result.command is not None:
            span.set_attribute("qa.tool.command", redact(result.command))
        if result.exit_code is not None:
            span.set_attribute("qa.tool.exit_code", result.exit_code)
        for key in ("method", "route", "status_code"):
            if key in result.data:
                span.set_attribute(f"qa.http.{key}", result.data[key])
        # Files this call left in the run directory (spec v3 §4.4): junit report, Playwright evidence folders.
        produced = [p for p in (result.data.get("junit"), *result.data.get("evidence", ())) if isinstance(p, str)]
        if produced:
            span.set_attribute("qa.artifact.path", produced)
        if isinstance(result.data.get("isolation"), str):
            span.set_attribute("qa.isolation.level", result.data["isolation"])
        if denials := result.data.get("l1_denials"):
            span.set_attribute("qa.isolation.denials", len(denials))
        results = result.data.get("results") or []
        if results:
            span.set_attribute("qa.test.count", len(results))
            span.set_attribute("qa.test.collection_errors", sum(1 for r in results if "::" not in r["node_id"] and r["outcome"] == "ERROR"))
        for r in results:
            if r["outcome"] in ("FAIL", "ERROR"):
                span.add_event(
                    "qa.test.result",
                    {"qa.test.id": r["node_id"], "qa.test.outcome": r["outcome"], "qa.test.message": redact(r.get("message", ""))[:500]},
                    timestamp=self._inst.clock.now_ns(),
                )
        _scan_secret(self._inst, "tool.stdout", getattr(span, "name", "tool"), result.stdout)
        record_content(self._inst, span, "stdout", result.stdout, tail=True)
        if message := _tool_failure(result):
            span.set_status(Status(StatusCode.ERROR, redact(message)))


class AgentTools:
    """The tool view one agent gets: every call is made as that agent (and so passes the gate for it).

    Repeated-call guard: after MAX_IDENTICAL_FAILURES failures of the same call (tool + identical arguments),
    another identical request is refused without executing (RepeatedToolCallError, rule R6).
    """

    MAX_IDENTICAL_FAILURES = 2

    def __init__(self, traced: TracedToolRegistry, agent: str) -> None:
        self._traced, self.agent = traced, agent
        self._failures: dict[str, int] = {}

    def call(self, name: str, **args: Any) -> ToolResult:
        from tools.registry import RepeatedToolCallError

        # A new revision round rewrites the files, so the same arguments are a new call there.
        key = json.dumps([name, args, self._traced.round], sort_keys=True, default=str)

        def precheck() -> None:
            if self._failures.get(key, 0) >= self.MAX_IDENTICAL_FAILURES:
                raise RepeatedToolCallError(f"{name} with identical arguments already failed {self._failures[key]} times; not retrying")

        try:
            result = self._traced.call_as(self.agent, name, args, precheck)
        except Exception as exc:
            if type(exc).__name__ != "RepeatedToolCallError":
                self._failures[key] = self._failures.get(key, 0) + 1
            raise
        if result.ok:
            self._failures.pop(key, None)
        else:
            self._failures[key] = self._failures.get(key, 0) + 1
        return result


class TracedAgent(Generic[In, Out]):
    def __init__(
        self,
        agent: Any,
        inst: Instrumentation,
        output_attributes: Callable[[Out], Mapping[str, Any]] | None = None,
    ) -> None:
        self._agent, self._inst, self._output_attributes = agent, inst, output_attributes
        self.name: str = agent.name

    @property
    def inner(self) -> Any:
        return self._agent

    def run(self, inp: In, attributes: Mapping[str, Any] | None = None) -> Out:
        with start_span(self._inst, f"agent.{self.name}", {"qa.agent.name": self.name, **(attributes or {})}) as span:
            out = self._agent.run(inp)
            if self._output_attributes:
                span.set_attributes(dict(self._output_attributes(out)))
            record_content(self._inst, span, "output", _to_text(out))
            return out


def traced_agent(agent: Any, inst: Instrumentation, output_attributes: Callable[[Any], Mapping[str, Any]] | None = None) -> TracedAgent:
    return TracedAgent(agent, inst, output_attributes)


class RunHandle:
    def __init__(self, span: Span, inst: Instrumentation) -> None:
        self._span, self._inst = span, inst

    @property
    def trace_id(self) -> str:
        return _ids(self._span)[0]

    def set_verdict(self, verdict: str) -> None:
        self._span.set_attribute("qa.verdict", verdict)

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.set_attribute(key, value)

    def fail(self, exc: BaseException) -> None:
        mark_error(self._inst, self._span, exc)


@contextmanager
def traced_run(
    inst: Instrumentation,
    requirement_id: str,
    sut_bugs: Sequence[str] = (),
    *,
    run_id: str | None = None,
    prompt_version: str | None = None,
    dataset: str | None = None,
) -> Iterator[RunHandle]:
    attrs: dict[str, Any] = {"qa.run.requirement_id": requirement_id, "qa.run.sut_bugs": list(sut_bugs)}
    for key, value in (("qa.run.id", run_id), ("qa.run.prompt_version", prompt_version), ("qa.run.dataset", dataset)):
        if value is not None:
            attrs[key] = value
    with start_span(inst, "qa.run", attrs, root=True) as span:
        yield RunHandle(span, inst)
