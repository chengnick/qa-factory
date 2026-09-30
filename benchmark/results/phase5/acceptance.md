# Phase 5: formal evaluation (held-out test set)

**Status: evaluation complete; attribution labelled by the owner for `human_layer` (2026-09-30); `targets_injected_bug` not labelled.**

Spec v3.2 §13 Phase 5. Runs 2026-09-28, started 15:55–19:29 UTC. Machine-generated numbers: [summary.md](summary.md) / [summary.json](summary.json).

## Conditions (frozen before the test set was unsealed)

`benchmark/frozen.yaml` (sha256 `e919ca70…`), written at `219dfbe`, committed `60ad3be`. Every run checked every field before starting:
`gemini-3.5-flash-lite` (the only model the provider reported), temperature 0, prompt `v3` (sha256 pinned), lockfile / policy / conftest hashes, isolation L1 (= L1a, the in-process audit hook; see spec §8.2), one revision round. Runs executed at commit `60ad3be`, clean worktree.

18 combinations × 5 rounds = 90 runs: dev set (B02–B04 and their 3 clean requirements) and test set (7 held-out bugs B01, B05–B10 and 5 clean requirements).

## Results

| | Dev set (B02–B04, used for prompt tuning) | **Test set (held out, first run)** |
|---|---|---|
| True detection rate (cross-validated) | 9/9 (95% CI 70–100%) | **25/28 = 89%** (range 71–100% per round, 95% CI 73–96%) |
| Detection when the pipeline completed | 9/9 | 25/27 = 92% (95% CI 77–98%) |
| Surface false-positive rate (what a user sees) | 0/9 | **4/20 = 20%** (95% CI 8–42%) |
| False-positive rate after cross-validation | 0/9 | 0/20 |
| Test health | 66/66 | 139/161 = 86% |
| Environment-block rate | 12/30 | 12/60 |
| INCONCLUSIVE / UNKNOWN classifications | 0 / 0 of 21 | 0 / 0 of 63 |
| Mean tokens / duration per run | 4 791 / 126 s | 4 757 / 134 s |

Per held-out bug (cross-validated, blocked runs excluded): B01 3/4, **B05 2/4**, B06 4/4, B07 4/4, B08 4/4, B09 4/4, B10 4/4.

## What the numbers say

- **The UI requirement is the weak spot.** Three of the four surface false positives are REQ-004 clean runs (the fourth is REQ-009), and both B05 misses are REQ-004 runs whose UI tests failed on the buggy *and* the clean build (TEST_BROKEN), i.e. the generated UI tests were wrong, not blind to the bug. Cross-validation turned all four false positives into TEST_BROKEN; without it a user would have seen "defect found" on a correct system in 1 of 5 clean runs.
- **One agent failure (B01, round 4):** the test-design step returned a 10-case plan, above the limit of 8; its output was rejected as invalid (AGENT / INVALID_OUTPUT, rule R5), so no test ran.
- **Dev vs test:** the dev set scored 9/9 but on only 9 usable runs; the test set's 89% (n=28) is the main figure. The dev-set tuning in Phase 2 does not show as a large dev/test gap, but the dev sample is too small to measure one.

## Provider outage (ENV_BLOCKED: 23 × 503, 1 × 504)

24 of 90 runs were blocked by the provider (layer PROVIDER): 23 by Gemini HTTP 503 "model is experiencing high demand" (rule R3) and 1 by HTTP 504 "Deadline expired" (`RUN-20260928-165559-6431`, rule R4, symptom TIMEOUT). They are all 18 runs of round 1 and the 6 dev runs of round 2, consecutively (runs started 15:55–17:01 UTC). They were recorded as they happened and not re-run or moved to another model (spec v3 §13 Phase 2R rule). Consequences: they are excluded from the other metrics' denominators, round 1 contributes nothing, and the dev set has 3 usable rounds instead of 5.

## Attribution accuracy (spec v3 §11.2)

Labelled by the owner on 2026-09-30 ([sheet.csv](../../labels/phase5/sheet.csv), committed in `9617645` before scoring; scores in [score.md](../../labels/phase5/score.md) / `score.json`). Sample: 40 of the 84 classified failures, stratified by the classifier's layer (SUT 18, TEST 10, PROVIDER 11, AGENT 1; seed 20260928; row order shuffled with seed 20260929). The sheet showed only the raw error message; cross-validation outcomes and the classifier's answers were withheld (`sheet_key.csv`, `key.json`).

| Rows | Layer agreement (human vs classifier) |
|---|---|
| **diff rows: generated tests judged by cross-validation (main figure)** | **24/28 = 86%** (Wilson 95% CI 69–94%) |
| llm / agent rows (reported apart: the exception type decides them) | 12/12 (95% CI 76–100%) |
| all rows | 36/40 = 90% (95% CI 77–96%) |

By the classifier's layer: SUT 18/18 (CI 82–100%), TEST 6/10 (CI 31–83%), PROVIDER 11/11, AGENT 1/1. No row was labelled UNKNOWN.

**All four disagreements are the same case:** the classifier said TEST (rule R12: the test fails on the buggy and on the clean build), the owner said SUT. They are four REQ-004 UI tests of "API 錯誤時於錯誤區顯示訊息" (`RUN-20260928-185129-7150#0`, `-191850-A65E#1`, `-181752-C9AE#2`, `-183440-2857#1`). Reading the SUT page (`sut/static/index.html`, not run): it does show API errors, but the tests' way of provoking one does not produce an API error. For example `?project=99999` selects no project, so the page makes no task request and the error area stays empty; and when page initialisation fails, `data-ready` is never set, which one test waits for. The requirement does not say whether an unknown preselected project is an error to display. So this is a specification gap: "the system should have shown something" (SUT) and "the test assumed behaviour the requirement does not state" (TEST) are both defensible. The labels are kept as the owner made them. It also qualifies the "UI tests are the weak spot" finding above: part of the UI test breakage comes from this unclear requirement, not only from badly written tests.

`targets_injected_bug` (did the failing test really exercise the injected bug): **not labelled.** The owner left the column empty; the 16 rows where only `n.a.` is possible were filled mechanically by the assistant at the owner's request, and the 24 rows needing a yes / no judgement stay open. The assistant did not fill them: they are manual labels.

Limits: the sample is drawn from failures the classifier had already attributed, so the figure measures precision, not misses; there is one labeller, the author; n = 28 for the main figure.

## Not done

- **Prompt-injection layer 2 (§11.4): deferred** by the owner's decision. Authoring the attack documents was not done by the assistant; if resumed, the owner writes the injection documents and the harness only measures (generate-only, no execution).
- `targets_injected_bug` labels: not made (24 rows open). Attribution accuracy itself is measured (above).
