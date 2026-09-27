# Evaluation summary: dataset `dev`, 1 rounds

- Model: `gemini-3.5-flash-lite` (reported by provider: gemini-3.5-flash-lite), temperature 0.0
- Prompt version: `v3`; git commit `05cb0fbcfc4d55283f3bebbe46bb31fc10482f2c` (dirty: False); lockfile sha256 `e727f4d1a5cfe7854fa25fe3b625d58cf7cfa6ab70c40f891ddaa2d674326cd6`

## Metrics (spec v3 §11.2)

Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.

| Metric | Value |
|---|---|
| True detection rate (cross-validated) | 100% (range 100%–100%, rounds n=1; pooled 3/3, 95% CI 44%–100%) |
| Detection rate when the pipeline completed (AGENT_FAILED excluded) | 100% (range 100%–100%, rounds n=1; pooled 3/3, 95% CI 44%–100%) |
| Surface detection rate (unverified) | 100% (range 100%–100%, rounds n=1; pooled 3/3, 95% CI 44%–100%) |
| **False-positive rate (surface, main figure)** | 0% (range 0%–0%, rounds n=1; pooled 0/3, 95% CI 0%–56%) |
| False-positive rate (cross-validated; 0 by construction) | 0% (range 0%–0%, rounds n=1; pooled 0/3, 95% CI 0%–56%) |
| Test health | 100% (range 100%–100%, rounds n=1; pooled 23/23, 95% CI 86%–100%) |
| Environment-block rate | 0% (range 0%–0%, rounds n=1; pooled 0/6, 95% CI 0%–39%) |
| INCONCLUSIVE rate (no rule matched a failure) | 0% (range 0%–0%, rounds n=1; pooled 0/6, 95% CI 0%–39%) |
| UNKNOWN classification rate | 0/3 classifications (6 runs with classification) |

## Per-bug detection

| Bug | Cross-validated | Pipeline completed | AGENT_FAILED | Surface | ENV_BLOCKED |
|---|---|---|---|---|---|
| B02 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| B03 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| B04 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |

Cost: mean tokens 5341.833333333333, mean duration 33.31666666666666 s, n=6

## Runs

| Round | run_id | Requirement | Bugs | Surface | Verdict | Cross-validation | detected / broken / tests | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | `RUN-20260927-143251-EF3A` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 1 | `RUN-20260927-143345-ACF4` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 1 | `RUN-20260927-143437-284C` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 1 | `RUN-20260927-143521-226F` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 1 | `RUN-20260927-143607-8CF2` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 1 | `RUN-20260927-143651-723A` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 5 |  |
