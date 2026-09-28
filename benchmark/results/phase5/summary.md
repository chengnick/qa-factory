# Evaluation summary: dataset `phase5`, 5 rounds

- Model: `gemini-3.5-flash-lite` (reported by provider: gemini-3.5-flash-lite), temperature 0.0
- Prompt version: `v3`; git commit `60ad3be985a06cee57bf85c25ebcf1bf86e64705` (dirty: False); lockfile sha256 `e727f4d1a5cfe7854fa25fe3b625d58cf7cfa6ab70c40f891ddaa2d674326cd6`
- Frozen conditions: `benchmark/frozen.yaml` sha256 `e919ca706db4e80b32fc9b50495dbe28dda966af9a6a89718dc1e542b9e9f703`, every field matched

## Dev set (B02-B04; used for prompt tuning)

Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.

| Metric | Value |
|---|---|
| True detection rate (cross-validated) | 100% (range 100%–100%, rounds n=3; pooled 9/9, 95% CI 70%–100%) |
| Detection rate when the pipeline completed (AGENT_FAILED and R20 excluded) | 100% (range 100%–100%, rounds n=3; pooled 9/9, 95% CI 70%–100%) |
| Surface detection rate (unverified) | 100% (range 100%–100%, rounds n=3; pooled 9/9, 95% CI 70%–100%) |
| **False-positive rate (surface, main figure)** | 0% (range 0%–0%, rounds n=3; pooled 0/9, 95% CI 0%–30%) |
| False-positive rate (cross-validated; 0 by construction) | 0% (range 0%–0%, rounds n=3; pooled 0/9, 95% CI 0%–30%) |
| Test health | 100% (range 100%–100%, rounds n=3; pooled 66/66, 95% CI 94%–100%) |
| Environment-block rate | 40% (range 0%–100%, rounds n=5; pooled 12/30, 95% CI 25%–58%) |
| INCONCLUSIVE rate (no rule matched a failure) | 0% (range 0%–0%, rounds n=3; pooled 0/18, 95% CI 0%–18%) |
| UNKNOWN classification rate | 0/21 classifications (30 runs with classification) |

### Per-bug detection

| Bug | Cross-validated | Pipeline completed | AGENT_FAILED | R20 (LLM request rejected) | Surface | ENV_BLOCKED |
|---|---|---|---|---|---|---|
| B02 | 3/3 | 3/3 | 0/3 | 0/3 | 3/3 | 2/5 |
| B03 | 3/3 | 3/3 | 0/3 | 0/3 | 3/3 | 2/5 |
| B04 | 3/3 | 3/3 | 0/3 | 0/3 | 3/3 | 2/5 |

Cost: mean tokens 4791.2, mean duration 126.25333333333333 s, n=30

## Test set (held out; first run after the freeze)

Mean and range are over per-round rates; the 95% CI is a Wilson interval on the pooled count.

| Metric | Value |
|---|---|
| True detection rate (cross-validated) | 89% (range 71%–100%, rounds n=4; pooled 25/28, 95% CI 73%–96%) |
| Detection rate when the pipeline completed (AGENT_FAILED and R20 excluded) | 92% (range 83%–100%, rounds n=4; pooled 25/27, 95% CI 77%–98%) |
| Surface detection rate (unverified) | 93% (range 86%–100%, rounds n=4; pooled 26/28, 95% CI 77%–98%) |
| **False-positive rate (surface, main figure)** | 20% (range 0%–40%, rounds n=4; pooled 4/20, 95% CI 8%–42%) |
| False-positive rate (cross-validated; 0 by construction) | 0% (range 0%–0%, rounds n=4; pooled 0/20, 95% CI 0%–16%) |
| Test health | 86% (range 79%–91%, rounds n=4; pooled 139/161, 95% CI 80%–91%) |
| Environment-block rate | 20% (range 0%–100%, rounds n=5; pooled 12/60, 95% CI 12%–32%) |
| INCONCLUSIVE rate (no rule matched a failure) | 0% (range 0%–0%, rounds n=4; pooled 0/48, 95% CI 0%–7%) |
| UNKNOWN classification rate | 0/63 classifications (60 runs with classification) |

### Per-bug detection

| Bug | Cross-validated | Pipeline completed | AGENT_FAILED | R20 (LLM request rejected) | Surface | ENV_BLOCKED |
|---|---|---|---|---|---|---|
| B01 | 3/4 | 3/3 | 1/4 | 0/4 | 3/4 | 1/5 |
| B05 | 2/4 | 2/4 | 0/4 | 0/4 | 3/4 | 1/5 |
| B06 | 4/4 | 4/4 | 0/4 | 0/4 | 4/4 | 1/5 |
| B07 | 4/4 | 4/4 | 0/4 | 0/4 | 4/4 | 1/5 |
| B08 | 4/4 | 4/4 | 0/4 | 0/4 | 4/4 | 1/5 |
| B09 | 4/4 | 4/4 | 0/4 | 0/4 | 4/4 | 1/5 |
| B10 | 4/4 | 4/4 | 0/4 | 0/4 | 4/4 | 1/5 |

Cost: mean tokens 4757.020833333333, mean duration 133.53833333333333 s, n=60

## Runs

| Round | Set | run_id | Requirement | Bugs | Surface | Verdict | Cross-validation | detected / broken / tests | Note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | dev | `RUN-20260928-155504-FAB3` | REQ-005 | B02 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | dev | `RUN-20260928-155922-7E6E` | REQ-007 | B03 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | dev | `RUN-20260928-160109-7064` | REQ-002 | B04 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | dev | `RUN-20260928-160246-6A64` | REQ-005 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | dev | `RUN-20260928-160421-20F0` | REQ-007 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | dev | `RUN-20260928-160555-F38A` | REQ-002 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-160732-FE5D` | REQ-003 | B01 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-160908-C60F` | REQ-004 | B05 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-161044-D783` | REQ-002 | B06 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-161422-9E5B` | REQ-008 | B07 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-161605-5994` | REQ-006 | B08 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-161743-8500` | REQ-009 | B09 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-161937-0167` | REQ-004 | B10 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-162123-E13C` | REQ-003 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-162309-3DAB` | REQ-004 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-162510-6EF7` | REQ-008 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-163051-8228` | REQ-006 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 1 | test | `RUN-20260928-163233-85EC` | REQ-009 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | dev | `RUN-20260928-163539-3FF2` | REQ-005 | B02 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | dev | `RUN-20260928-163732-D1BD` | REQ-007 | B03 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | dev | `RUN-20260928-163927-E9F3` | REQ-002 | B04 | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | dev | `RUN-20260928-165410-ADFB` | REQ-005 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | dev | `RUN-20260928-165559-6431` | REQ-007 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMTimeoutError: Gemini API error 504: Deadline expired before operation could complete. |
| 2 | dev | `RUN-20260928-170140-B71D` | REQ-002 | (clean) | ENV_BLOCKED | ENV_BLOCKED | not run | - | LLMUnavailableError: Gemini API error 503: This model is currently experiencing high demand. Spikes in demand are usuall |
| 2 | test | `RUN-20260928-170329-47C4` | REQ-003 | B01 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 2 / 0 / 4 |  |
| 2 | test | `RUN-20260928-170912-4D7C` | REQ-004 | B05 | TEST_BROKEN | TEST_BROKEN | COMPLETE | 0 / 4 / 4 |  |
| 2 | test | `RUN-20260928-171056-7231` | REQ-002 | B06 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 2 | test | `RUN-20260928-171736-F27F` | REQ-008 | B07 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 2 | test | `RUN-20260928-172359-37F0` | REQ-006 | B08 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 2 |  |
| 2 | test | `RUN-20260928-173103-415B` | REQ-009 | B09 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 1 / 3 |  |
| 2 | test | `RUN-20260928-173745-F4EA` | REQ-004 | B10 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 1 / 4 |  |
| 2 | test | `RUN-20260928-174148-65D7` | REQ-003 | (clean) | FLAKY | FLAKY | COMPLETE | 0 / 0 / 5 |  |
| 2 | test | `RUN-20260928-174355-26C5` | REQ-004 | (clean) | TEST_BROKEN | TEST_BROKEN | COMPLETE | 0 / 3 / 3 |  |
| 2 | test | `RUN-20260928-174631-3A58` | REQ-008 | (clean) | FLAKY | FLAKY | COMPLETE | 0 / 0 / 4 |  |
| 2 | test | `RUN-20260928-175444-B6BC` | REQ-006 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 2 |  |
| 2 | test | `RUN-20260928-175749-606D` | REQ-009 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 3 | dev | `RUN-20260928-175913-2D76` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | dev | `RUN-20260928-180028-3F50` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 3 | dev | `RUN-20260928-180556-9DB8` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | dev | `RUN-20260928-180805-7490` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 5 |  |
| 3 | dev | `RUN-20260928-181021-B9B1` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 3 | dev | `RUN-20260928-181257-1270` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 5 |  |
| 3 | test | `RUN-20260928-181458-5BFA` | REQ-003 | B01 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 5 |  |
| 3 | test | `RUN-20260928-181752-C9AE` | REQ-004 | B05 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 2 / 1 / 4 |  |
| 3 | test | `RUN-20260928-182434-256B` | REQ-002 | B06 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | test | `RUN-20260928-182648-B528` | REQ-008 | B07 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 3 | test | `RUN-20260928-182814-1703` | REQ-006 | B08 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 3 | test | `RUN-20260928-183010-313C` | REQ-009 | B09 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 3 | test | `RUN-20260928-183145-5B06` | REQ-004 | B10 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 1 / 3 |  |
| 3 | test | `RUN-20260928-183333-8046` | REQ-003 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 3 | test | `RUN-20260928-183440-2857` | REQ-004 | (clean) | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 2 / 3 |  |
| 3 | test | `RUN-20260928-183609-CE36` | REQ-008 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 3 | test | `RUN-20260928-183719-AAC8` | REQ-006 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 2 |  |
| 3 | test | `RUN-20260928-183816-5CEB` | REQ-009 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | dev | `RUN-20260928-183913-5DD9` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 4 | dev | `RUN-20260928-184018-C99A` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 4 | dev | `RUN-20260928-184114-087E` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 4 | dev | `RUN-20260928-184208-C902` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | dev | `RUN-20260928-184255-18A2` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 4 | dev | `RUN-20260928-184343-04B4` | REQ-002 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | test | `RUN-20260928-184430-E57F` | REQ-003 | B01 | AGENT_FAILED | AGENT_FAILED | not run | - | AgentOutputError: test plan has 10 cases; at most 8 allowed |
| 4 | test | `RUN-20260928-184456-8DF1` | REQ-004 | B05 | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 3 / 3 |  |
| 4 | test | `RUN-20260928-184615-6E56` | REQ-002 | B06 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 4 | test | `RUN-20260928-184702-7657` | REQ-008 | B07 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 4 | test | `RUN-20260928-184751-2FE3` | REQ-006 | B08 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 2 |  |
| 4 | test | `RUN-20260928-184840-6B23` | REQ-009 | B09 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 4 | test | `RUN-20260928-184921-AB17` | REQ-004 | B10 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 1 / 3 |  |
| 4 | test | `RUN-20260928-185041-C48F` | REQ-003 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | test | `RUN-20260928-185129-7150` | REQ-004 | (clean) | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 1 / 4 |  |
| 4 | test | `RUN-20260928-185243-CDC6` | REQ-008 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 4 | test | `RUN-20260928-185330-1B75` | REQ-006 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 2 |  |
| 4 | test | `RUN-20260928-185409-630B` | REQ-009 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 5 | dev | `RUN-20260928-185449-9A01` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | dev | `RUN-20260928-185529-D62B` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | dev | `RUN-20260928-185618-982E` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 2 |  |
| 5 | dev | `RUN-20260928-185712-27DC` | REQ-005 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 5 | dev | `RUN-20260928-185806-D690` | REQ-007 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 3 |  |
| 5 | dev | `RUN-20260928-185937-4032` | REQ-002 | (clean) | FLAKY | FLAKY | COMPLETE | 0 / 0 / 4 |  |
| 5 | test | `RUN-20260928-190326-2D86` | REQ-003 | B01 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | test | `RUN-20260928-190713-1408` | REQ-004 | B05 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 2 / 1 / 3 |  |
| 5 | test | `RUN-20260928-190935-079D` | REQ-002 | B06 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | test | `RUN-20260928-191150-63FB` | REQ-008 | B07 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 4 |  |
| 5 | test | `RUN-20260928-191437-3540` | REQ-006 | B08 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 2 |  |
| 5 | test | `RUN-20260928-191622-2198` | REQ-009 | B09 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 0 / 3 |  |
| 5 | test | `RUN-20260928-191850-A65E` | REQ-004 | B10 | DEFECT_FOUND | DEFECT_FOUND | COMPLETE | 1 / 1 / 3 |  |
| 5 | test | `RUN-20260928-192210-F2F1` | REQ-003 | (clean) | PASS | PASS | COMPLETE | 0 / 0 / 4 |  |
| 5 | test | `RUN-20260928-192351-7FF9` | REQ-004 | (clean) | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 1 / 4 |  |
| 5 | test | `RUN-20260928-192539-518D` | REQ-008 | (clean) | FLAKY | FLAKY | COMPLETE | 0 / 0 / 4 |  |
| 5 | test | `RUN-20260928-192709-CFAB` | REQ-006 | (clean) | FLAKY | FLAKY | COMPLETE | 0 / 0 / 2 |  |
| 5 | test | `RUN-20260928-192930-EFF1` | REQ-009 | (clean) | DEFECT_FOUND | TEST_BROKEN | COMPLETE | 0 / 1 / 3 |  |
