# Phase 0 reference-test matrix

- Generated: 2026-09-25T01:31:46+08:00
- Python 3.11.9 · win32
- Expected: a reference test **FAIL**s iff its bug is enabled, otherwise **PASS**es.
- Cell: actual outcome; ✅ matches expectation, ❌ does not. Bold = the bug is enabled in that row.

| SUT_BUGS | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 | B10 | Result | Time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `(none)` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.9s |
| `B01` | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.9s |
| `B02` | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.9s |
| `B03` | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.9s |
| `B04` | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.1s |
| `B05` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 17.0s |
| `B06` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.1s |
| `B07` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | ✅ PASS | OK | 15.1s |
| `B08` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | ✅ PASS | OK | 15.1s |
| `B09` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | ✅ PASS | OK | 15.1s |
| `B10` | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | ✅ PASS | **✅ FAIL** | OK | 20.0s |
| `all` | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | **✅ FAIL** | OK | 20.9s |

**120/120 cells match** → PASS
