# Development log

Per-phase detail moved here from the README when it was restructured (2026-10-05). The text is kept as it was, except: links point from `docs/`, and three outdated statements were corrected (the Phase 1 LLM note, the classifier rule range R1–R21, and the UNKNOWN examples in [limitations.md](limitations.md)). Phases are listed newest first; the Isolation section describes the current state.

## Results (Phase 5; [details](../benchmark/results/phase5/acceptance.md))

- Bugs were split into a dev set (3, used for prompt tuning) and a held-out test set (7, run once after freezing prompt, model and conditions in [benchmark/frozen.yaml](../benchmark/frozen.yaml)).
- **Held-out true detection rate: 89%** (25/28 runs, per-round range 71–100%, 95% CI 73–96%), verified by running every generated test against both the buggy and the clean build. Dev set: 9/9.
- **False-positive rate on the clean build: 20% before cross-validation** (4/20, 95% CI 8–42%), **0/20 after it**. A user of the pipeline alone would see "defect found" on a correct system in about 1 of 5 clean runs; three of the four came from the UI requirement, whose generated UI tests are the weakest part (both B05 misses were broken UI tests).
- Failure-layer attribution matched the owner's manual labels in **24 of 28** sampled test failures (86%, 95% CI 69–94%); 12/12 for LLM / agent failures, reported apart. All four disagreements are one case, a UI requirement that does not say what the page must do (classifier: test broken; owner: system at fault). One labeller, the author; the sample measures precision, not misses ([score](../benchmark/labels/phase5/score.md)).
- 24 of 90 runs were blocked by a Gemini outage (23 × HTTP 503 "high demand", 1 × HTTP 504 timeout) and are reported separately, not re-run with another model.
- Deterministic fault-injection suite covering tool misuse, provider outages, retry loops, permission violations and test weakening across revision rounds.
- Isolation level: **L1a** (in-process audit hook, not an OS sandbox); L1b (OS level) not done (see *Isolation*). Prompt-injection resistance of the model (spec layer 2) was **not measured**.

## Property-based tests (after the evaluation)

The one exception to the feature freeze: tests only ([tests/property/](../tests/property/), Hypothesis from [requirements-test.lock](../requirements-test.lock), installed on top of `requirements.lock` so the frozen lockfile hash is unchanged). They check, over generated inputs: a refused tool call never executes; every spelling of a protected, evidence or other-run path is refused and judged the same; URLs that only look like the SUT are refused; the verdict always follows the priority order, ignores observation order and is never PASS when no test ran; removing assertions from a failing test that then passes always triggers W01. Five deliberately injected bugs (monkeypatch, no code edited) are each caught; the cross-validation decision table is enumerated in full.

They found one real bug: the generated-code check accepted `http://127.0.0.1:<port>@evil.test`, an extra port digit and `127.0.0.1:<port>.evil.test` as the SUT (prefix match without a boundary). It was fixed with the owner's approval; no recorded run had a hard-coded URL, so no result changes. Post-evaluation changes are listed in [benchmark/frozen_amendments.yaml](../benchmark/frozen_amendments.yaml); `python -m evaluation.frozen check --model gemini-3.5-flash-lite` reports them next to the (still matching) frozen conditions.

```bash
pip install -r requirements.lock -r requirements-test.lock
python -m pytest tests/property                              # ci profile: fixed examples, 100 each
HYPOTHESIS_PROFILE=full python -m pytest tests/property      # 5000 random examples each
```

## Phase 4 (evidence, Workflow Evaluator, L1 guard)

- **Revision rounds** ([pipeline.py](../pipeline.py)): the pipeline can run automation + QA again while tests fail, up to `max_rounds`, for an automation agent that declares `revises = True`. **The real AutomationAgent does not revise, so live runs have exactly one round** (prompt stays v3; an LLM-driven revision step would need a new prompt version and a dev-set re-run). Each round's tests are saved read-only to `generated/roundN/` and listed with sha256 and per-test results in `rounds.json`. Spans carry `qa.test.round`.
- **Playwright evidence** ([generated/conftest.py](../generated/conftest.py)): a failed UI test leaves `playwright/{call}/{test}/trace.zip`, `screenshot.png` and `console.log`; tool spans list what they produced in `qa.artifact.path`. The owner conftest's hash is in `meta.json` (`conftest_sha256`).
- **Workflow Evaluator** ([evaluation/workflow.py](../evaluation/workflow.py), spec v3 §9): deterministic rules over the whole run. W01 weakened test, W02 removed failing test, W03 expected value rewritten to the observed one, W04 executed security event, W05 missing or changed evidence in acceptance mode. Output `workflow_eval.json`, `WORKFLOW_VIOLATION` / `GOAL_DRIFT` security events. **It does not change the verdict**; it is reported next to it. Because live runs have one round, W01–W03 are shown on scripted histories ([testing/scripted_rounds.py](../testing/scripted_rounds.py)), not on real model behaviour.
- **L1 guard** ([tools/l1_guard.py](../tools/l1_guard.py)): see *Isolation* below. In-process, not an OS sandbox.
- **Final report**: every run ends with `report.json` (spec v3 §12). `python -m evaluation.report <run dirs> --out DIR` rebuilds reports for existing runs elsewhere.
- **Offline check on the 30 Phase 2R runs**: no W01–W04 violation; W05 lists only the files later phases added (`security_events.json`, `classification.json`, `rounds.json`), as expected for the older layout.

### Phase 3.5 (policy file, CI)

- **Policy file** ([config/agent_policy.yaml](../config/agent_policy.yaml), [permissions/policy.py](../permissions/policy.py)): the permission table, protected and evidence paths, and the generated-code rules. Validated strictly at startup: an invalid policy stops the program before any run exists. Every permission check, allowed or denied, is a `qa.permission.check` span event and is counted in `meta.json`.
- **CI** ([.github/workflows/ci.yml](../.github/workflows/ci.yml)): runs the tests (`-m "not live"`) and the Phase 0 matrix on ubuntu-latest and windows-latest with the pinned Python version (`.python-version`) and `requirements.lock`, plus a non-blocking Python 3.14 canary. No real LLM, no secrets. CI verifies one Python version on two operating systems, nothing more.

### Phase 3 (failure attribution, permission gate, fault injection)

### Architecture fact: tool routing is fixed

Agents decide which tool to call and with which arguments; **the LLM only produces content** (a requirement summary, a test plan, test source code). It never chooses a tool. So "the LLM called an unknown tool", "passed wrong arguments" or "kept repeating a failing call" cannot happen through the model in this pipeline.

The fault-injection scenarios reproduce those situations with `ScriptedAgent` ([testing/fake_agent.py](../testing/fake_agent.py)), an agent whose tool calls come from a script. **Those scenarios test the safeguards** (gate, registry, trace, classifier), **not the model's behaviour**. The same holds for prompt injection layer 1: FakeLLM plays a model that obeys the injection, and the tests show the safeguards hold. How often a real model would obey is a separate, statistical question (spec v3 §11.4, Phase 5).

### Phase 3 (spec v3 §5, §7, §10)

- **Classifier** ([classification/](../classification/)): the rule table R1–R21 plus R11U (R19–R21 added after Phase 3), ordered specific before general. Every classification records `matched_rule` and `evidence`; a failure no rule matches is `UNKNOWN`, and the run is `INCONCLUSIVE`. The verdict order is ENV_BLOCKED > AGENT_FAILED > DEFECT_FOUND > TEST_BROKEN > INCONCLUSIVE > MISSED > FLAKY > PASS. Each run writes `classification.json`.
- **Permission gate and security events** ([permissions/gate.py](../permissions/gate.py), [security/events.py](../security/events.py)): spec v3 §8.1 per agent; `security_events.json` per run.
- **Static check of generated tests** ([tools/code_policy.py](../tools/code_policy.py)): a check, not a sandbox.
- **Fault injection**: `pytest tests/agent_faults/ tests/agent_security/` runs 104 tests in about 6 s (13–16 s wall clock), identical across 20 consecutive runs. Details in [benchmark/results/phase3/acceptance.md](../benchmark/results/phase3/acceptance.md).
- **Phase 2R re-classified offline**: `python -m evaluation.classify_runs`. All 30 verdicts are reproduced.

### Phase 2R (re-acceptance of Phase 2 with cross-validation)

Install the exact locked versions (spec v3 D13):

```bash
pip install -r requirements.lock
pip install --no-deps -e .
```

### Phase 2R (spec v3 §6, §11)

- **Cross-validation** ([evaluation/differential.py](../evaluation/differential.py)): the final generated tests run once on a **fresh bug SUT** and once on a **fresh clean SUT**. Both builds use the same file order, tools, retry policy and whitelisted environment, and every fresh SUT starts from the same seed (users 1–4, no projects). Results are compared per pytest node id (§6.2):

  | Bug build | Clean build | Decision |
  |---|---|---|
  | FAIL | PASS | bug caught (R11) |
  | FAIL | FAIL | broken test (R12) |
  | PASS | FAIL | broken test (R13) |
  | ERROR | anything | broken test (R10) |
  | PASS | PASS | not caught |

  Each build starts with a SUT health check. If either check fails, cross-validation is `ENV_BLOCKED`: no test is judged and none counts toward test health. The pipeline's own QA run only gives the **surface verdict**. Output: `differential.json`, `pytest/bug_build.log`, `pytest/clean_build.log`, and an `evaluation.differential` span in the same trace.
- **Multi-round runner**: `python -m evaluation.run --dataset dev --rounds 5 --llm gemini --model gemini-3.5-flash-lite --results-dir benchmark/results/phase2r` ([evaluation/run.py](../evaluation/run.py)).
  - Combinations are interleaved round by round, and every run is copied to the results directory after a secret scan.
  - Live runs refuse a dirty git worktree, and `--dataset test` is refused while `benchmark/frozen.yaml` does not exist.
  - Metrics are in [evaluation/metrics.py](../evaluation/metrics.py): mean, range, n, and per-bug detection.

### Phase 2.5 (minimal fixes, spec v3 §13)

- **Evidence**: every run writes `artifacts/{run_id}/` (`run_id` = `RUN-YYYYMMDD-HHMMSS-XXXX`) and nothing deletes it automatically. `meta.json` records the trace_id, model, temperature, prompt version, dataset, git commit and lockfile hash. The root span carries `qa.run.id`, `qa.run.prompt_version` and `qa.run.dataset`.
- **Dev / test split**: B02, B03 and B04 are the dev set; the other seven bugs are sealed until Phase 5 ([benchmark/datasets.py](../benchmark/datasets.py)). `app.py` refuses sealed bugs unless `--allow-test-set` is passed.
- **Prompt pinning**: prompts are pinned to [agents/version.py](../agents/version.py) (currently `v3`). A test fails if a prompt changes without a version bump.
- **PROVIDER layer** (spec v3 R2–R4): LLM 429, 5xx, timeouts and connection failures are marked `qa.failure.layer=PROVIDER` and end the run as `ENV_BLOCKED`. The verdict for an aborted run follows the exception type (`agents/report.py::EXCEPTION_VERDICTS`), not a blanket `AGENT_FAILED`.
- **Isolation L0+**: see *Isolation* below.

### Phase 2

- **Gemini adapter**: `llm/adapters/gemini.py` uses the `google-genai` SDK in JSON mode with `temperature=0`. SDK retries are off; 429s and timeouts are retried through `with_retry()`, so every attempt is a span.
- **Real tools**: `tools/` has `file_write` (the tool writes only inside the run's `generated/`), `pytest` / `playwright` (run tests in a subprocess against the SUT), and `http_request`. Arguments are checked against a parameter schema before a tool runs.
- **Per-run workspace**: each live run gets `artifacts/{run_id}/`, and generated tests are written and executed there (see *Isolation* below).
- **Agent context**: agents get the API reference in [docs/sut-api.md](sut-api.md) and the owner-written fixtures in [generated/conftest.py](../generated/conftest.py), which is read-only for agents.
- **SUT startup**: `sut/launcher.py` starts the SUT with any set of bug flags. The pipeline and the reference tests share it.

**Acceptance** ([phase2_acceptance.md](../benchmark/results/phase2_acceptance.md)): 5 of 6 bugged runs genuinely detected (B02, B03, B04, each checked by hand), 1 of 6 clean runs a false positive. Model: `gemini-3.5-flash-lite` (the larger Flash models returned 503 at run time).

Set up the key once. Create `.env` in the repo root with `GEMINI_API_KEY=...`. It is git-ignored and never printed or traced.

```bash
python app.py --requirement REQ-005 --llm gemini --sut-bugs B02    # starts a SUT with B02 enabled
QA_LIVE=1 pytest tests/llm/test_gemini_live.py                     # optional live smoke test
```

### Phase 1

- **LLM**: `llm/client.py` defines the `LLMClient` Protocol. At the time of Phase 1 only the scripted `FakeLLM` existed and no real LLM was connected; the Gemini adapter arrived in Phase 2.
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
- **Seeded bugs**: 10 bugs in 8 categories, listed in [benchmark/bugs.yaml](../benchmark/bugs.yaml). They are switched on with `SUT_BUGS`, and every injection point is an `is_enabled("Bxx")` call in `sut/app.py`.
- **Requirements**: [benchmark/requirements/](../benchmark/requirements/) has REQ-001 to REQ-009.
- **Reference tests**: [benchmark/reference_tests/](../benchmark/reference_tests/) has one hand-written, black-box test per bug. API bugs are tested with httpx and UI bugs with Playwright.

```bash
SUT_BUGS=B01,B04 uvicorn sut.app:app
python -m benchmark.matrix         # acceptance matrix -> benchmark/results/phase0_matrix.md
pytest tests                       # flag mechanism + manifest consistency
```

## Isolation (current level: L1a, in-process audit hook; L1b not done)

> **Policy decides what an agent should be allowed to do. Isolation determines what it actually can do.**
>
> - Policy: tool-level allowlist in [config/agent_policy.yaml](../config/agent_policy.yaml), validated at startup, hash recorded in every trace (`qa.policy.hash`) and in `meta.json` (`policy_hash`)
> - Isolation: **L1a**, enforced in-process by an audit hook in the test subprocess. It applies the L1 rules of spec v3 §8.2 (read-only repo and evidence, network only to the SUT) to what CPython audits. **L1b**, the OS-level version (restricted account or token), is not done; neither is a container (L2).
>
> The value `L1` in older records means L1a: `benchmark/frozen.yaml` (`isolation: L1`), each run's `meta.json` / `report.json` (`isolation_level`), the span attribute `qa.isolation.level` and `PytestTool(isolation="L1")`. Those records are not changed.

| Control | Status |
|---|---|
| Agents can reach tools only through the registry, with a parameter schema check | ✅ in-process (L0) |
| `file_write` refuses paths outside the run's `generated/`, the owner conftest, the round snapshots `generated/roundN/`, and non-`.py` files | ✅ in-process check on the tool (L0) |
| Generated tests run in a subprocess whose working directory is the run workspace `artifacts/{run_id}/` | ✅ (L0+) |
| The subprocess gets whitelisted environment variables only; `GEMINI_API_KEY`, other tokens and `PYTHONPATH` are dropped (tested in `tests/tools/test_pytest_isolation.py`) | ✅ (L0+) |
| The workspace has its own `pytest.ini`, so the repo root is not on `sys.path` | ✅ (L0+) |
| Permission gate per agent (spec v3 §8.1): tools per agent; `file_write` paths judged after `resolve()` + `normcase()` (own `generated/` → protected → evidence → other); `http_request` only to SUT paths. Refusals never execute and are recorded in `security_events.json` | ✅ Phase 3 (L0, in-process) |
| Static check of generated test code (AST): allowed imports only; no `open` / `exec` / `eval` / `compile` / `__import__` / `getattr` / `__builtins__`; no `__dict__` / `__class__` / `__subclasses__`; no hard-coded non-SUT URLs. A violating file is not run (`AGENT_FAILED`, rule R18). **This is a check, not a sandbox**: determined code can get around it | ✅ Phase 3 (L0+) |
| Generated code can write only its own junit report, the Playwright evidence folder and a private temp dir; `sut/`, `benchmark/`, the run's own evidence and every other path are read-only; the repo `.env` cannot be read (tested in `tests/tools/test_l1_guard.py`) | ✅ Phase 4 (L1a, **in-process audit hook**) |
| Network from generated code: name lookups and connections only to the SUT | ✅ Phase 4 (L1a, in-process audit hook) |
| Network from the browser: every request that is not for the SUT is aborted by the page fixture (the browser runs outside Python) | ✅ Phase 4 (fixture route; the test code could remove it) |
| Processes: only the Playwright driver may be started; `os.system`, exec, spawn, fork refused. Native code: no new libraries, no raw memory reads | ✅ Phase 4 (L1a, in-process audit hook) |
| Credentials (checked 2026-10-08, read-only): tokens in environment variables (`GITHUB_TOKEN`, `GH_TOKEN`, `GIT_ASKPASS`, `SSH_AUTH_SOCK`, ...) never reach generated code (`ENV_WHITELIST` in `tools/pytest_tool.py`; `tests/tools/test_pytest_isolation.py`). The git credential helper (`manager`, backed by the Windows Credential Manager) and the Credential Manager API need a new process or a new native library, both refused under L1a (`test_processes_and_native_code_are_refused` in `tests/tools/test_l1_guard.py`); under L0+ only the static check stands in the way. Credential files in the user's home directory (`~/.ssh`, `~/.netrc`, `~/.git-credentials`, GitHub CLI config) are **readable** under L0+ and L1a: L1a refuses reads only of the repo's `.env` (`deny_read` in `tools/pytest_tool.py`; `test_reading_the_repo_is_allowed`), and `HOME`, `USERPROFILE` and `APPDATA` are passed through. Reading them takes code that gets past the static check | ✅ environment tokens (L0+); ✅ helper and Credential Manager (L1a); ❌ credential files not protected |
| What the L1a guard cannot stop: operations CPython does not audit (e.g. `_winapi.CreateFile` on Windows), functions of libraries loaded before the hook (pytest, colorama, httpx, trio are preloaded; colorama holds `kernel32`), and anything done by the browser process itself. Refusals are logged to a file the test could rewrite; the refusal itself is the protection | ⚠️ known gaps |
| L1b: restricted OS account or token for the test subprocess | ❌ not done (needs administrator changes) |
| L2: container with read-only mounts and an isolated network | ❌ (container mode proposed, not built) |

Refusals raise `PermissionError` in the test, are recorded as `PERMISSION_DENIED` security events (`action: l1:<event>`, `executed: false`) and counted on the tool span (`qa.isolation.denials`). `report.json` states the level (`isolation_level`) and what it means (`isolation_note`). `PytestTool(isolation="L0+")` switches the guard off; the test suite uses that as a control to show the same write succeeding without it.

The pipeline is one-way (tests run after the LLM has finished writing them), so test output never flows back into an LLM prompt.
That limits what a test could leak to the model, but it is not a security boundary.
