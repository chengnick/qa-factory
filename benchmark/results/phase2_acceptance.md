# Phase 2 acceptance: live runs

> **The traces are lost.** All trace files from these runs were deleted after acceptance (`rm -rf traces`).
> The trace_ids below come from terminal output saved during the runs. The "checked cause" column comes
> from inspecting pytest output and trace artifacts while the files still existed. Nothing here can be
> re-verified from retained traces.

- Date: 2026-09-25
- Bugs exercised: **B02, B03, B04 only** (plus the clean SUT). These three are the development set. The
  other seven bugs are the sealed test set and must not be run before Phase 4.
- Model: `gemini-3.5-flash-lite`, temperature 0, free tier. Runs 1–2 used `gemini-3.6-flash`.
  `gemini-3.8-flash`, `3.7-flash` and `3.6-flash` returned 503 (overloaded) at run time.
- Verdicts come from the provisional rules (`agents/report.py`). There is no automated layer attribution
  yet (Phase 3), so "checked cause" is a manual judgement.

## Prompt versions

| Version | Change | Status |
|---|---|---|
| v1 | Original prompts | **prompt tuning** |
| v2 | test_design rules: track entity state, enumerate small sets, quote the criterion | **prompt tuning** |
| v3 | automation prompt shows correct fixture usage; pytest tool separates `AssertionError` from other test-code exceptions (TEST_BROKEN) | final |

Runs under v1 and v2 were part of tuning the prompts while watching B02/B03/B04. They are not
independent measurements, and v3 was tuned on the same three bugs. Treat all numbers as development-set
results.

## All 26 runs

| # | Model | Prompt | Requirement | SUT_BUGS | Verdict | Checked cause | Correct? | trace_id |
|---|---|---|---|---|---|---|---|---|
| 1 | 3.6-flash | v1 (tuning) | REQ-005 | B02 | AGENT_FAILED | 503 on all 5 attempts of agent.requirement | n/a (provider) | `39e30e7f69f5974898396bb257b237a5` |
| 2 | 3.6-flash | v1 (tuning) | REQ-005 | B02 | AGENT_FAILED | agent.requirement OK on attempt 5; agent.test_design 503 ×5 | n/a (provider) | `f7d5d064e8efc15da15a0cffbe09b9ee` |
| 3 | lite | v1 (tuning) | REQ-005 | B02 | PASS | only `done → todo` tested; `done → in_progress` never tried | ❌ miss | `f732090bd33939e2bc05fe9816d22abf` |
| 4 | lite | v1 (tuning) | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500, expected 422 | ✅ real B04 | `6a6700a441efa22f87f4c657d9797d76` |
| 5 | lite | v1 (tuning) | REQ-007 | B03 | DEFECT_FOUND | non-member `GET /api/tasks/{id}` returned 200, expected 403 | ✅ real B03 | `409272a142961158b5534b4642cb0246` |
| 6 | lite | v1 (tuning) | REQ-005 | (none) | DEFECT_FOUND | test design chained one task through `done`, then expected `done → in_progress` to succeed | ❌ false positive (broken test) | not recorded |
| 7 | lite | v1 (tuning) | REQ-002 | (none) | PASS | | ✅ | not recorded |
| 8 | lite | v1 (tuning) | REQ-007 | (none) | PASS | | ✅ | not recorded |
| 9 | lite | v2 (tuning) | REQ-005 | B02 | DEFECT_FOUND | `done → in_progress` returned 200, expected 409 | ✅ real B02 | `cb6e668539e18aad4d2e6d33197ad47d` |
| 10 | lite | v2 (tuning) | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500 | ✅ real B04 | `a868ff44caef78c4ba69ed751e29a9ab` |
| 11 | lite | v2 (tuning) | REQ-007 | B03 | DEFECT_FOUND | fixture misuse (`new_project` passed as the project id) led to `assert 422 == 201` | ❌ right verdict, wrong reason | `0b5771e80c98d2c77909c4a9d9f53274` |
| 12 | lite | v2 (tuning) | REQ-005 | (none) | DEFECT_FOUND | fixture misuse: `as_user` not called, `AttributeError` in all 4 tests | ❌ false positive (broken test) | `d49eb05d03251d95f3411ff7dec76007` |
| 13 | lite | v2 (tuning) | REQ-002 | (none) | PASS | | ✅ | `9cf26df1f517623b7aaa1133bbdf3233` |
| 14 | lite | v2 (tuning) | REQ-007 | (none) | PASS | | ✅ | `66dfd88aeacdca16afd9da96535db957` |
| 15 | lite | v3 round 1 | REQ-005 | B02 | DEFECT_FOUND | `done → in_progress` returned 200, expected 409 | ✅ real B02 | `2ed3fa3b01d9d3dd38da9829e382bb41` |
| 16 | lite | v3 round 1 | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500 | ✅ real B04 | `9cf8fd0d33f64f8aaaef3ce8bebf32ae` |
| 17 | lite | v3 round 1 | REQ-007 | B03 | DEFECT_FOUND | non-member read returned 200, expected 403 | ✅ real B03 | `cd1a1461b0a2ed5e3c2e6e8d80a97a73` |
| 18 | lite | v3 round 1 | REQ-005 | (none) | PASS | | ✅ | `a193241d1fbac789a1bc2c05a798b86a` |
| 19 | lite | v3 round 1 | REQ-002 | (none) | PASS | | ✅ | `7453db7c21b3f03d8cde5203860124c4` |
| 20 | lite | v3 round 1 | REQ-007 | (none) | DEFECT_FOUND | test used a non-integer id `/api/tasks/non-existent-tid` and expected 404; the SUT returns 422 | ❌ false positive (broken test) | `2b2465325c9bb85a55ff5b53ea57f5bd` |
| 21 | lite | v3 round 2 | REQ-005 | B02 | PASS | only `done → todo` tested | ❌ miss | `18fc18885462e02fb638526a37763cdf` |
| 22 | lite | v3 round 2 | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500 | ✅ real B04 | `a18bc0d5ece21e17a6d57c00ab054776` |
| 23 | lite | v3 round 2 | REQ-007 | B03 | DEFECT_FOUND | non-member read returned 200 | ✅ real B03 | `50921585962cc1d6c3697caddb089059` |
| 24 | lite | v3 round 2 | REQ-005 | (none) | PASS | | ✅ | `aadf1b10f95075171bf68863b73cd05c` |
| 25 | lite | v3 round 2 | REQ-002 | (none) | PASS | | ✅ | `da073c26e530a39deff814ef6de6cde4` |
| 26 | lite | v3 round 2 | REQ-007 | (none) | PASS | | ✅ | `b3cf8e1c89568a81d64753a1b0475f15` |

Runs 1–2 were recorded as AGENT_FAILED under the rules of the time. Under the later rule (provider
503/429 → ENV_BLOCKED) they would be ENV_BLOCKED.

## Summary

| Scope | Bugged runs genuinely detected | Clean-SUT false positives |
|---|---|---|
| v3 (final prompts), 12 runs | 5/6 (B02 1/2, B03 2/2, B04 2/2) | 1/6 |
| v1–v2 (tuning), 12 runs | 4/6 real (runs 4, 5, 9, 10); 1 miss; 1 right-verdict-wrong-reason | 2/6 |
| Provider failures | runs 1–2 (503) | |

- **Acceptance criterion** ("DEFECT_FOUND for at least 3 API bugs"): met on the development set. B02, B03 and
  B04 were each genuinely detected under v3. The result is not independent of tuning, because v3 was tuned
  on these same bugs.
- **Not traced at all** (by design, they bypass the traced pipeline): 6 further Gemini calls returned 503. One came from
  `tests/llm/test_gemini_live.py`, five from model-availability probe scripts.

## Known gaps, for Phase 3

- A wrong test that still fails with an `AssertionError` is indistinguishable from a real defect without the
  reference-test cross-check (rules R8/R9). Runs 11 and 20 are this case.
- Single runs are noisy (B02 detected 1/2 under v3). Phase 4 runs each combination 3 times.
