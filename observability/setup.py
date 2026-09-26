"""TracerProvider construction. The provider is returned, never installed globally, so tests stay isolated."""

from __future__ import annotations

import threading
from collections import defaultdict

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

SERVICE_NAME = "qa-factory"


class SpanCollector(SpanProcessor):
    """Keeps finished spans per trace in memory so the pipeline can classify its own run before the root ends."""

    def __init__(self) -> None:
        self._spans: dict[int, list[ReadableSpan]] = defaultdict(list)
        self._lock = threading.Lock()

    def on_end(self, span: ReadableSpan) -> None:
        with self._lock:
            self._spans[span.context.trace_id].append(span)

    def spans(self, trace_id: int | str) -> list[ReadableSpan]:
        key = int(trace_id, 16) if isinstance(trace_id, str) else trace_id
        with self._lock:
            return list(self._spans.get(key, []))


def create_tracer_provider(*exporters: SpanExporter, collector: SpanCollector | None = None) -> TracerProvider:
    """Synchronous processors: a span is exported the moment it ends (deterministic, no background thread)."""
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    if collector is not None:
        provider.add_span_processor(collector)
    for exporter in exporters:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def new_instrumentation(clock, sink=None, *exporters: SpanExporter):
    """(provider, Instrumentation) with a span collector attached; the standard way to set up a run."""
    from observability.instrument import Instrumentation, NullContentSink

    collector = SpanCollector()
    provider = create_tracer_provider(*exporters, collector=collector)
    return provider, Instrumentation(get_tracer(provider), clock, sink or NullContentSink(), collector)


def get_tracer(provider: TracerProvider) -> Tracer:
    return provider.get_tracer(SERVICE_NAME)
