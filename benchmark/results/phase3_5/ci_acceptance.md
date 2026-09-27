# Phase 3.5 acceptance: CI

Spec v3.1 §13 Phase 3.5 and §15.5. Repository: `chengnick/qa-factory` (private). Date 2026-09-27.

## Result on `main` (CI #4, commit `226aea2`; CI #5 at `c8e6039` also green)

| Job | Result | Tests | Skipped (reason) | pytest time | Phase 0 matrix |
|---|---|---|---|---|---|
| test (ubuntu-latest, Python 3.11 from `.python-version`, `requirements.lock`) | ✅ | 656 passed | 13: 11 Windows-only gate path cases (case-insensitive paths, backslashes, Windows absolute forms), 2 Windows 8.3 short-path tests | 61.4 s | ran, 28 s |
| test (windows-latest, same) | ✅ | 668 passed | 1: POSIX-only gate test (`/etc/...` is not absolute on Windows) | 74.6 s | ran, 31 s |
| canary (ubuntu-latest, Python 3.14, pyproject, not blocking) | ✅ | 656 passed | 13 (as ubuntu) | 61.0 s | not run (by design) |

1 test deselected everywhere: the live Gemini test (`-m "not live"`). Total workflow time 3 min 20 s.

## Failures found by the first CI runs (fixed before the result above)

- **CI #1, #2, windows-latest: 70 failures.** The runner's TEMP is an 8.3 short path (`C:\Users\RUNNER~1\...`); `file_write` and the pytest tool compared resolved (long) test paths with the unresolved workspace. A Phase 2 bug that local paths never exposed. Fixed in `846a7ef` (tools resolve their root), regression test `tests/tools/test_short_paths.py`; the full suite also passes locally with TEMP set to a short path.
- **CI #2, canary (Python 3.14): 4 UI failures.** Python 3.14 on Linux starts subprocesses through `os.posix_spawn` after the `subprocess.Popen` audit event; the L1 guard refused `os.posix_spawn` outright, so the Playwright driver could not start. Fixed in `226aea2`: every process-start event is judged by the program it starts.
- **CI #4, windows-latest: 1 warning.** A test decoded subprocess output with the runner's cp1252 code page. Fixed in `c8e6039`.
- CI #3 was cancelled by the next push (concurrency group).

## Deliberate failures (branches deleted afterwards)

| Branch | Change | CI | Failed step | Evidence uploaded |
|---|---|---|---|---|
| `ci-deliberate-failure-pytest` (`c88c9f5`) | one test that always fails | #6 red | step 6 "Tests (no live LLM)" on ubuntu, windows and canary | ✅ `ci-evidence-ubuntu-latest` (12 KB), `ci-evidence-windows-latest` (12.1 KB) |
| `ci-deliberate-failure-matrix` (`3ef2d23`) | B09 reference test skipped (pytest passes, the matrix expects PASS/FAIL) | #7 red | step 7 "Phase 0 acceptance matrix" on ubuntu and windows; canary green (it does not run the matrix) | ✅ `ci-evidence-ubuntu-latest` (13.7 KB), `ci-evidence-windows-latest` (13.8 KB) |

Both branches were deleted locally and on GitHub after the check; their runs and artifacts stay in the Actions history (artifact retention 14 days).
