# Evaluation summary: dataset `dev`, 5 rounds

- Model: `gemini-3.5-flash-lite` (reported by provider: gemini-3.5-flash-lite), temperature 0.0
- Prompt version: `v3`; git commit `32c5e1ed40c76567dfbaa3efb30bf384e4c8eb28` (dirty: True); lockfile sha256 `e727f4d1a5cfe7854fa25fe3b625d58cf7cfa6ab70c40f891ddaa2d674326cd6`
- Summary regenerated from the 30 run directories on 2026-09-26T12:44:39+00:00 (commit `75d04e6172822790dc36d143a886ab3e19806a71`); no pipeline was re-run.

## Metrics (spec v3 §11.2)

Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.

| Metric | Value |
|---|---|
| True detection rate (cross-validated) | 80% (range 67%–100%, rounds n=5; pooled 12/15, 95% CI 55%–93%) |
| Surface detection rate (unverified) | 80% (range 67%–100%, rounds n=5; pooled 12/15, 95% CI 55%–93%) |
| **False-positive rate (surface, main figure)** | 7% (range 0%–33%, rounds n=5; pooled 1/15, 95% CI 1%–30%) |
| False-positive rate (cross-validated; 0 by construction) | 0% (range 0%–0%, rounds n=5; pooled 0/15, 95% CI 0%–20%) |
| Test health | 98% (range 94%–100%, rounds n=5; pooled 101/103, 95% CI 93%–99%) |
| Environment-block rate | 0% (range 0%–0%, rounds n=5; pooled 0/30, 95% CI 0%–11%) |

## Per-bug detection

| Bug | Cross-validated | Surface | ENV_BLOCKED |
|---|---|---|---|
| B02 | 3/5 | 3/5 | 0/5 |
| B03 | 5/5 | 5/5 | 0/5 |
| B04 | 4/5 | 4/5 | 0/5 |

Cost: mean tokens 5113.5, mean duration 30.81 s, n=30

## Runs

| Round | run_id | Requirement | Bugs | Surface | Verdict | Cross-validation | detected / broken / tests | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | `RUN-20260925-160546-73BF` | REQ-005 | B02 | PASS | MISSED | COMPLETE | 0 / 0 / 6 |  |
| 1 | `RUN-20260925-160630-19B8` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 1 | `RUN-20260925-160714-7485` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 1 | `RUN-20260925-160754-1661` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 1 | `RUN-20260925-160844-FFB7` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 1 | `RUN-20260925-160935-E01D` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 2 | `RUN-20260925-161022-8C22` | REQ-005 | B02 | PASS | MISSED | COMPLETE | 0 / 0 / 5 |  |
| 2 | `RUN-20260925-161132-894F` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 2 | `RUN-20260925-161217-D84D` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 2 | `RUN-20260925-161300-9E1B` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 2 | `RUN-20260925-161347-60D6` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 2 | `RUN-20260925-161448-162F` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 3 | `RUN-20260925-161532-CAA1` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | `RUN-20260925-161615-9CE6` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 3 | `RUN-20260925-161703-D276` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | `RUN-20260925-161747-CF2A` | REQ-005 | (clean) | TEST_BROKEN | TEST_BROKEN | COMPLETE | 0 / 1 / 1 |  |
| 3 | `RUN-20260925-161823-0279` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 3 | `RUN-20260925-161907-808D` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | `RUN-20260925-161951-52A1` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 5 |  |
| 4 | `RUN-20260925-162051-4B53` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 4 | `RUN-20260925-162140-FD00` | REQ-002 | B04 | AGENT_FAILED | AGENT_FAILED | not run | - | AgentOutputError: LLM output is not valid JSON: Expecting property name enclosed in double quotes: line 16 column 7 (cha |
| 4 | `RUN-20260925-162200-4DA6` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | `RUN-20260925-162242-4188` | REQ-007 | (clean) | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 1 / 3 |  |
| 4 | `RUN-20260925-162323-26D9` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 5 | `RUN-20260925-162403-2580` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | `RUN-20260925-162445-0518` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 5 | `RUN-20260925-162526-8372` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | `RUN-20260925-162609-DB83` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 5 | `RUN-20260925-162650-B731` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 5 | `RUN-20260925-162731-E98A` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
