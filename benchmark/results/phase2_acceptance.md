# Phase 2 acceptance: live runs

- Date: 2026-09-25
- Model: `gemini-3.5-flash-lite`, temperature 0, free tier. `gemini-3.8-flash`, `3.7-flash` and `3.6-flash` returned 503 (overloaded) at run time.
- Each failing assertion was checked by hand against the seeded bug; see the "Checked cause" column.
- Verdicts come from the provisional rules (`agents/report.py`), not yet from the Phase 3 classifier.

## Final prompts (two rounds)

| Round | Requirement | SUT_BUGS | Verdict | Checked cause | Correct? |
|---|---|---|---|---|---|
| 1 | REQ-005 | B02 | DEFECT_FOUND | `done → in_progress` returned 200, expected 409 | ✅ real B02 |
| 1 | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500, expected 422 | ✅ real B04 |
| 1 | REQ-007 | B03 | DEFECT_FOUND | non-member `GET /api/tasks/{id}` returned 200, expected 403 | ✅ real B03 |
| 1 | REQ-005 | (none) | PASS | | ✅ |
| 1 | REQ-002 | (none) | PASS | | ✅ |
| 1 | REQ-007 | (none) | DEFECT_FOUND | test used a non-integer id `/api/tasks/non-existent-tid` and expected 404; the SUT returns 422 | ❌ false positive (broken test) |
| 2 | REQ-005 | B02 | PASS | only `done → todo` tested; `done → in_progress` never tried | ❌ miss |
| 2 | REQ-002 | B04 | DEFECT_FOUND | 101-char title returned 500 | ✅ real B04 |
| 2 | REQ-007 | B03 | DEFECT_FOUND | non-member read returned 200 | ✅ real B03 |
| 2 | REQ-005 | (none) | PASS | | ✅ |
| 2 | REQ-002 | (none) | PASS | | ✅ |
| 2 | REQ-007 | (none) | PASS | | ✅ |

- **Real detections**: 5/6 bugged runs (B02 1/2, B04 2/2, B03 2/2).
- **False positives on the clean SUT**: 1/6.
- **Acceptance** ("DEFECT_FOUND for at least 3 API bugs"): met. B02, B04 and B03 were each genuinely detected, all three within round 1.

## Earlier rounds (kept for honesty)

- **Original prompts**: B02 missed. The REQ-005 clean run was a false positive: the test design chained one task through `done` and then expected `done → in_progress` to succeed.
- **After the test-design prompt rules** (track entity state, enumerate small sets, quote the criterion): 2 of 4 DEFECT_FOUND verdicts came from fixture misuse (the model did not call the `as_user` / `new_project` factories).
- **Fixes applied**:
  - The automation prompt now shows correct fixture usage.
  - The pytest tool separates `AssertionError` failures from other exceptions raised by test code; the latter now count as TEST_BROKEN.

## Known gaps, for Phase 3

- A wrong test that still fails with an `AssertionError` is indistinguishable from a real defect without the reference-test cross-check (rules R8/R9). The round-1 REQ-007 false positive is this case.
- Single runs are noisy (B02 detected 1/2). Phase 4 runs each combination 3 times.
