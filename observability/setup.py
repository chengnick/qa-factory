"""TracerProvider construction. The provider is returned, never installed globally, so tests stay isolated."""

from __future__ import annotations

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

SERVICE_NAME = "qa-factory"


def create_tracer_provider(*exporters: SpanExporter) -> TracerProvider:
    """Synchronous processors: a span is exported the moment it ends (deterministic, no background thread)."""
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    for exporter in exporters:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def get_tracer(provider: TracerProvider) -> Tracer:
    return provider.get_tracer(SERVICE_NAME)
