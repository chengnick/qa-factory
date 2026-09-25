# QA Factory

A QA agent pipeline with end-to-end tracing and rule-based failure attribution, evaluated against a small app with seeded bugs. Spec: [docs/spec.md](docs/spec.md) (v3).

## Current status: Phase 2.5 done; Phase 2 acceptance to be redone (Phase 2R)

Install the exact locked versions (spec v3 D13):

```bash
pip install -r requirements.lock
pip install --no-deps -e .
```

### Phase 2.5 (minimal fixes, spec v3 §13)

- **Evidence**: every run writes `artifacts/{run_id}/` (`run_id` = `RUN-YYYYMMDD-HHMMSS-XXXX`) and nothing deletes it automatically. `meta.json` records the trace_id, model, temperature, prompt version, dataset, git commit and lockfile hash. The root span carries `qa.run.id`, `qa.run.prompt_version` and `qa.run.dataset`.
- **Dev / test split**: B02, B03 and B04 are the dev set; the other seven bugs are sealed until Phase 5 ([benchmark/datasets.py](benchmark/datasets.py)). `app.py` refuses sealed bugs unless `--allow-test-set` is passed.
- **Prompt pinning**: prompts are pinned to [agents/version.py](agents/version.py) (currently `v3`). A test fails if a prompt changes without a version bump.
- **PROVIDER layer** (spec v3 R2–R4): LLM 429, 5xx, timeouts and connection failures are marked `qa.failure.layer=PROVIDER` and end the run as `ENV_BLOCKED`. The verdict for an aborted run follows the exception type (`agents/report.py::EXCEPTION_VERDICTS`), not a blanket `AGENT_FAILED`.
- **Isolation L0+**: see *Isolation* below.

### Phase 2

- **Gemini adapter**: `llm/adapters/gemini.py` uses the `google-genai` SDK in JSON mode with `temperature=0`. SDK retries are off; 429s and timeouts are retried through `with_retry()`, so every attempt is a span.
- **Real tools**: `tools/` has `file_write` (the tool writes only inside the run's `generated/`), `pytest` / `playwright` (run tests in a subprocess against the SUT), and `http_request`. Arguments are checked against a parameter schema before a tool runs.
- **Per-run workspace**: each live run gets `artifacts/{run_id}/`, and generated tests are written and executed there (see *Isolation* below).
- **Agent context**: agents get the API reference in [docs/sut-api.md](docs/sut-api.md) and the owner-written fixtures in [generated/conftest.py](generated/conftest.py), which is read-only for agents.
- **SUT startup**: `sut/launcher.py` starts the SUT with any set of bug flags. The pipeline and the reference tests share it.

**Acceptance** ([phase2_acceptance.md](benchmark/results/phase2_acceptance.md)): 5 of 6 bugged runs genuinely detected (B02, B03, B04, each checked by hand), 1 of 6 clean runs a false positive. Model: `gemini-3.5-flash-lite` (the larger Flash models returned 503 at run time).

Set up the key once. Create `.env` in the repo root with `GEMINI_API_KEY=...`. It is git-ignored and never printed or traced.

```bash
python app.py --requirement REQ-005 --llm gemini --sut-bugs B02    # starts a SUT with B02 enabled
QA_LIVE=1 pytest tests/llm/test_gemini_live.py                     # optional live smoke test
```

### Phase 1

- **LLM**: `llm/client.py` defines the `LLMClient` Protocol. Only the scripted `FakeLLM` exists; no real LLM is connected yet.
- **Agents**: `agents/` has five minimal agents (requirement, test_design, automation, qa, report) with typed dataclass handoffs (`agents/contracts.py`). The LLM and tools are injected, and agents never import OpenTelemetry.
- **Tracing**: `observability/` builds on the OTel SDK. Spans are mounted around agents, the LLM and tools in `pipeline.py`. Every retry goes through `with_retry()`, which emits one `attempt` child span per try. Timestamps come from an injected clock. Secrets are redacted in spans, events, artifacts and trace files.
- **Output**: every run (fake or live) gets its own `artifacts/{run_id}/` directory (spec v3 §4.2). It is git-ignored and never deleted automatically. It contains:
  - `meta.json`: run_id ↔ trace_id, requirement, model, prompt version, dataset, SUT bugs, git commit, lockfile hash, verdict
  - `trace.json`: the trace (spec v2 §3.4 format, carried over by v3)
  - `prompts/`: full-size LLM inputs and outputs; `spans/`: other full-size content (agent outputs, stdout)
  - `generated/`: the tests the Automation agent wrote, plus a copy of the owner conftest
  - `reports/`: junit XML from each test run

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
SUT_BUGS=B01,B04 uvicorn sut.app:app
python -m benchmark.matrix         # acceptance matrix -> benchmark/results/phase0_matrix.md
pytest tests                       # flag mechanism + manifest consistency
```

## Known limitations

- **Fake runs are simulated.** `--llm fake` runs are fully scripted and use a simulated clock. `--llm gemini` runs use real tools and a real clock.
- **Free tier.** Gemini's free tier uses submitted content to improve Google products (only the public requirements and generated tests are sent). Its small quota can make runs slow, and runs fail when retries are exhausted.
- **Provisional verdict.** The verdict is computed by `agents/report.py::provisional_verdict`. Only the PROVIDER layer (R2–R4) is attributed so far; the full rule-based classifier arrives in Phase 3.
- **Playwright browser.** `requirements.lock` pins Playwright 1.61; run `playwright install chromium` if no matching browser is installed.
- **UI bugs are visible in the page source.** B05 and B10 are injected server-side by swapping JS snippets. The served page looks like naturally buggy code with no flag names, but a reader can still spot the bug by reading it.
- **Weak identity.** Users are identified only by the `X-User` header. There is no real authentication.
- **B01 needs multiple pages.** It only triggers when pagination has moved past the first page (`offset > 0`), so the single-page UI list is unaffected.
- **Partial isolation only.** See *Isolation* below.

## Isolation (current level: L0+)

Measured against spec v3 §8.2. Generated test code can still read and write local files until L1.

| Control | Status |
|---|---|
| Agents can reach tools only through the registry, with a parameter schema check | ✅ in-process (L0) |
| `file_write` refuses paths outside the run's `generated/`, the owner conftest, and non-`.py` files | ✅ in-process check on the tool (L0) |
| Generated tests run in a subprocess whose working directory is the run workspace `artifacts/{run_id}/` | ✅ (L0+) |
| The subprocess gets whitelisted environment variables only; `GEMINI_API_KEY`, other tokens and `PYTHONPATH` are dropped (tested in `tests/tools/test_pytest_isolation.py`) | ✅ (L0+) |
| The workspace has its own `pytest.ini`, so the repo root is not on `sys.path` | ✅ (L0+) |
| Network access from generated code is limited to the SUT | ❌ **not enforced** (L1, Phase 4) |
| Restricting which paths generated code can read or write | ❌ **not enforced.** Generated code can open any absolute path the OS user can access, including `sut/`, `benchmark/`, `.env` and the reference tests |
| Permission gate per agent (spec v3 §8.1 table) | ❌ Phase 3 |
| Container with read-only mounts (L2) | ❌ |

The pipeline is one-way (tests run after the LLM has finished writing them), so test output never flows back into an LLM prompt.
That limits what a test could leak to the model, but it is not a security boundary.
