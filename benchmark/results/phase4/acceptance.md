# Phase 4 acceptance: evidence, Workflow Evaluator, L1

Spec v3.2 §13 Phase 4. Date 2026-09-27, Windows 11, Python 3.11, `requirements.lock`. No real LLM was called in Phase 4.

## Acceptance criteria

| Criterion (spec §13 Phase 4) | Result | Where |
|---|---|---|
| Every §9.2 rule has firing and non-firing tests | ✅ W01 (1 firing, 4 non-firing incl. a legitimate fix), W02 (2 / 1), W03 (1 / 3 incl. substring and added-check cases), W04 (1 / 1), W05 (4 / 3) | `tests/workflow/test_workflow_rules.py`, `tests/workflow/test_record_workflow.py` |
| Test weakening simulated with `ScriptedRounds` is caught by W01 and marked `GOAL_DRIFT` | ✅ through the real pipeline, gate and FileWriteTool: `W01`, `GOAL_DRIFT: true`, `WORKFLOW_VIOLATION` + `GOAL_DRIFT` events on the root span, both rounds' files kept | `tests/agent_faults/test_workflow_scenarios.py::test_weakening_is_caught_by_w01_and_marked_goal_drift` |
| Under L1, generated test code cannot write into `benchmark/` and `sut/` | ✅ refused with `PermissionError`, file absent afterwards, one `l1:open` refusal reported. Control: the same kind of write succeeds with `isolation="L0+"` | `tests/tools/test_l1_guard.py` |

**How L1 is met (D22):** by an in-process audit hook, not by a restricted OS account. It stops what CPython audits (open, os.* file operations, sockets, subprocess, ctypes loading); it does not stop unaudited operations such as `_winapi.CreateFile`, or the browser process. README *Isolation* lists the gaps.

## Also delivered

- Playwright evidence of failed UI tests (`trace.zip`, `screenshot.png`, `console.log`), verified against the real SUT and Chromium, with no L1 refusals during a UI run; browser requests outside the SUT are aborted (`tests/integration/test_playwright_evidence.py`).
- `generated/roundN/` read-only snapshots, `rounds.json`, `qa.test.round`, `qa.artifact.path` (`tests/agents/test_revision_rounds.py`).
- `report.json` (§12) at the end of every run; a real dry-run evaluation (`evaluation.run`, fake LLM, real SUT, cross-validation) passes W05 with nothing missing and reports `isolation_level: L1` (`tests/evaluation/test_run.py`).

## Test runs

| Command | Result |
|---|---|
| `pytest -m "not live"` | 660 passed, 1 skipped (POSIX-only gate test on Windows), 1 deselected (live), 270.9 s |
| `pytest tests/agent_faults tests/agent_security` (§10.4: < 30 s, no real LLM) | 110 passed, 1 skipped, 6.0 s |
| Phase 4 tests only | 74 passed, 63.2 s |
| `python -m benchmark.matrix` | 120/120 cells match |

Not verified yet: the new tests on ubuntu (CI has not run; the repo is not pushed).

## Offline check on the Phase 2R runs

`evaluation.workflow` and `evaluation.report` were run over the 30 runs in `benchmark/results/phase2r/`, writing only to a scratch directory (nothing under `benchmark/` changed):

- W01–W04: no violations (the runs have one round and no executed security events).
- W05 (not in acceptance mode for this check): each run lacks exactly `security_events.json`, `classification.json` and `rounds.json`, the files Phases 3 and 4 added. Expected for the older layout; the runs are not modified.

## Not done

- **LLM-driven revision rounds** (D21): the real AutomationAgent does not revise, so W01–W03 have been shown on scripted histories only.
- **Container mode (L2)**: proposed, not built; it needs a Playwright image download (~2 GB) and running the SUT inside the container network.
- **Restricted OS account (L1 as §8.2 describes it)**: needs administrator changes; not done.
