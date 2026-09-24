# QA Factory

A QA agent pipeline with end-to-end tracing and rule-based failure attribution, evaluated against a small app with seeded bugs. Spec: [docs/spec-v2.md](docs/spec-v2.md).

## Current status: Phase 1 (agent skeleton and trace core)

### Phase 1

- **LLM**: `llm/client.py` defines the `LLMClient` Protocol. Only the scripted `FakeLLM` exists; no real LLM is connected yet.
- **Agents**: `agents/` has five minimal agents (requirement, test_design, automation, qa, report) with typed dataclass handoffs (`agents/contracts.py`). The LLM and tools are injected, and agents never import OpenTelemetry.
- **Tracing**: `observability/` builds on the OTel SDK. Spans are mounted around agents, the LLM and tools in `pipeline.py`. Every retry goes through `with_retry()`, which emits one `attempt` child span per try. Timestamps come from an injected clock. Secrets are redacted in spans, events, artifacts and trace files.
- **Output**: one `traces/{trace_id}.json` per run, plus full-size content in `traces/{trace_id}/artifacts/`.

```bash
python app.py --requirement REQ-005 --llm fake            # scenario: flaky (default) | pass | defect
pytest tests/observability                               # offline, no API key
```

### Phase 0 (SUT and benchmark)

- **SUT**: `sut/` is a TaskBoard app (FastAPI + in-memory SQLite + one HTML page) with users, projects, members and tasks that move through a status state machine.
- **Seeded bugs**: 10 bugs in 8 categories, listed in [benchmark/bugs.yaml](benchmark/bugs.yaml). They are switched on with `SUT_BUGS`, and every injection point is an `is_enabled("Bxx")` call in `sut/app.py`.
- **Requirements**: [benchmark/requirements/](benchmark/requirements/) has REQ-001 to REQ-009.
- **Reference tests**: [benchmark/reference_tests/](benchmark/reference_tests/) has one hand-written, black-box test per bug. API bugs are tested with httpx and UI bugs with Playwright.

```bash
pip install -e ".[dev]"            # plus `playwright install chromium` if no browser is present
SUT_BUGS=B01,B04 uvicorn sut.app:app
python -m benchmark.matrix         # acceptance matrix -> benchmark/results/phase0_matrix.md
pytest tests                       # flag mechanism + manifest consistency
```

## Known limitations

- **Fake runs only.** Phase 1 runs are fully scripted: the fake tools do not execute anything, and time runs on a simulated clock that starts at the current time.
- **Provisional verdict.** The verdict is computed by `agents/report.py::provisional_verdict`. The rule-based classifier and `layer` attribution arrive in Phase 3.
- **Minimal tool registry.** It has no parameter schema validation yet (Phase 2) and no permission gate yet (Phase 5).

- **UI bugs are visible in the page source.** B05 and B10 are injected server-side by swapping JS snippets. The served page looks like naturally buggy code with no flag names, but a reader can still spot the bug by reading it.
- **Weak identity.** Users are identified only by the `X-User` header. There is no real authentication.
- **B01 needs multiple pages.** It only triggers when pagination has moved past the first page (`offset > 0`), so the single-page UI list is unaffected.
- **No isolation between agents and the SUT yet.** Permission isolation is at level L0 (nothing enforced yet; see spec §7.2).
