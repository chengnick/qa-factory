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
    span.add_event(
        "exception",
        {"exception.type": type(exc).__name__, "exception.message": redact(str(exc))},
        timestamp=inst.clock.now_ns(),
    )
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
            record_content(self._inst, span, "completion", response.content)
            return response


def _tool_failure(result: ToolResult) -> str | None:
    if result.ok:
        return None
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else f"exit code {result.exit_code}"


class TracedToolRegistry:
    """Tool calls as tool.<name> spans; tools whose policy allows >1 attempt run through with_retry()."""

    def __init__(self, registry: ToolRegistry, inst: Instrumentation) -> None:
        self._registry, self._inst = registry, inst

    def call(self, name: str, **args: Any) -> ToolResult:
        attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name, "qa.tool.name": name}
        with start_span(self._inst, f"tool.{name}", attrs) as span:
            tool = self._registry.get(name)
            tool.validate(args)  # a schema violation never reaches the tool
            invoke = lambda: tool.fn(**args)  # noqa: E731
            if tool.retry.max_attempts > 1:
                outcome = with_retry(invoke, tool.retry, self._inst, failure_of=_tool_failure)
                result, attempts = outcome.value, outcome.attempts
            else:
                result, attempts = invoke(), 1
            self._annotate(span, result)
            return dataclasses.replace(result, attempts=attempts)

    def _annotate(self, span: Span, result: ToolResult) -> None:
        if result.command is not None:
            span.set_attribute("qa.tool.command", redact(result.command))
        if result.exit_code is not None:
            span.set_attribute("qa.tool.exit_code", result.exit_code)
        for key in ("method", "route", "status_code"):
            if key in result.data:
                span.set_attribute(f"qa.http.{key}", result.data[key])
        record_content(self._inst, span, "stdout", result.stdout, tail=True)
        if message := _tool_failure(result):
            span.set_status(Status(StatusCode.ERROR, redact(message)))


class TracedAgent(Generic[In, Out]):
    def __init__(
        self,
        agent: Any,
        inst: Instrumentation,
        output_attributes: Callable[[Out], Mapping[str, Any]] | None = None,
    ) -> None:
        self._agent, self._inst, self._output_attributes = agent, inst, output_attributes
        self.name: str = agent.name

    def run(self, inp: In) -> Out:
        with start_span(self._inst, f"agent.{self.name}", {"qa.agent.name": self.name}) as span:
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
