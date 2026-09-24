from __future__ import annotations

import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agents.contracts import RequirementInput
from observability.instrument import Instrumentation, MemoryContentSink
from observability.setup import create_tracer_provider, get_tracer
from pipeline import PipelineResult, run_pipeline
from testing import scripts
from testing.fake_clock import FakeClock


@dataclass
class Harness:
    exporter: InMemorySpanExporter
    provider: TracerProvider
    clock: FakeClock
    sink: MemoryContentSink
    inst: Instrumentation

    def spans(self) -> list[ReadableSpan]:
        return list(self.exporter.get_finished_spans())

    def named(self, name: str) -> list[ReadableSpan]:
        return [s for s in self.spans() if s.name == name]

    def one(self, name: str) -> ReadableSpan:
        matches = self.named(name)
        assert len(matches) == 1, f"expected one {name!r} span, got {len(matches)}"
        return matches[0]

    def children(self, parent: ReadableSpan) -> list[ReadableSpan]:
        kids = [s for s in self.spans() if s.parent is not None and s.parent.span_id == parent.context.span_id]
        return sorted(kids, key=lambda s: s.start_time)

    def tree(self, span: ReadableSpan | None = None) -> tuple:
        """(name, (child trees...)) built only from parent_span_id links."""
        if span is None:
            roots = [s for s in self.spans() if s.parent is None]
            assert len(roots) == 1, f"expected exactly one root span, got {[r.name for r in roots]}"
            span = roots[0]
        return (span.name, tuple(self.tree(c) for c in self.children(span)))

    def run(self, requirement_id: str = "REQ-005", scenario: str = "flaky", sut_bugs=("B02",), **kwargs) -> PipelineResult:
        return run_pipeline(
            RequirementInput(requirement_id, f"# {requirement_id}\ntext"),
            llm=kwargs.pop("llm", None) or scripts.fake_llm(requirement_id, self.clock),
            tools=kwargs.pop("tools", None) or scripts.fake_tools(requirement_id, scenario, self.clock),
            inst=self.inst,
            sut_bugs=sut_bugs,
            **kwargs,
        )


@pytest.fixture
def harness() -> Iterator[Harness]:
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider(exporter)
    clock = FakeClock()
    sink = MemoryContentSink()
    yield Harness(exporter, provider, clock, sink, Instrumentation(get_tracer(provider), clock, sink))
    provider.shutdown()


@pytest.fixture
def tmp_dir() -> Iterator[Path]:
    # Own temp dir: pytest's tmp_path base directory is not writable on every dev machine.
    with tempfile.TemporaryDirectory(prefix="qa-obs-") as d:
        yield Path(d)
