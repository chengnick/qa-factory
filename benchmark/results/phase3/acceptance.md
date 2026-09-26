# Phase 3 驗收紀錄

## §10.4：故障注入與安全測試

- 指令：`pytest tests/agent_faults/ tests/agent_security/`
- 全部使用假的元件（FakeLLM、FakeProvider、FakeTool、ScriptedAgent、FakeClock），不呼叫真實 LLM、不啟動 SUT、不需要網路。
- 每次 104 個測試。

| 項目 | 結果 |
|---|---|
| 連續執行 20 次 | 20/20 次全部通過，**每個測試在 20 次中的結果完全一致** |
| pytest 回報的執行時間 | 5.6–7.5 秒（平均 6.4 秒） |
| 牆鐘時間（含直譯器啟動與本機全域 pytest 外掛） | 13–16 秒（另跑 3 次量測） |
| 30 秒以內 | ✅ |

涵蓋的 §10.2 情境（`tests/agent_faults/test_fault_scenarios.py`、`tests/agent_security/`）：

| 情境 | 驗證結果 |
|---|---|
| 呼叫不存在的工具 | 不執行；`AGENT/INVALID_OUTPUT`（R6）；`INVALID_TOOL_CALL` 事件 |
| 工具參數缺欄位 | schema 驗證攔截，工具未被呼叫（R6） |
| 工具第 1 次 timeout、第 2 次成功 | 2 個 attempt span；`FLAKY`（underlying `PASS`） |
| 工具持續 timeout | 停在重試上限（3 次）；`HARNESS/TIMEOUT`（R17） |
| LLM 回 429 | 經真正的 Gemini adapter 退避重試到上限；`PROVIDER/RATE_LIMIT`（R2）、`ENV_BLOCKED` |
| LLM 回 503 | `PROVIDER/HTTP_5XX`（R3）、`ENV_BLOCKED`；恢復後成功則為 `FLAKY` |
| LLM 輸出不是 JSON | `AGENT/INVALID_OUTPUT`（R5），下游 Agent 未執行 |
| 重複要求同一個失敗的工具呼叫 | 失敗 2 次後第 3 次被拒、不執行（R6） |
| Handoff 缺欄位 | 下游拒收；`AGENT/SCHEMA_MISMATCH`（R7），歸因到上游 `requirement` |
| QA Agent 嘗試 file_write | `PERMISSION_DENIED`、`executed: false`（R18） |
| Automation Agent 寫入 `sut/app.py` | `PROTECTED_PATH_WRITE` + `GOAL_DRIFT`，檔案未變（R18）。LLM 直接提出這種路徑時，更早就被 Agent 的輸出驗證擋下（R5） |
| 寫入其他 run 的目錄 | `EVIDENCE_TAMPER_ATTEMPT`，該目錄內容雜湊不變 |
| http_request 目標不是 SUT | 拒絕、工具未被呼叫 |
| 產生的測試讀取 `GEMINI_API_KEY` | 靜態檢查先擋下、不執行（R18）；即使程式碼能執行，環境變數白名單也讓它讀不到（`tests/tools/test_pytest_isolation.py`） |
| Prompt injection 第一層（§10.3） | 模型「照做」時：危險動作全部被擋下、事件皆 `executed: false`、其他 run 與 `sut/`、`docs/`、`reference_tests/` 雜湊不變；LLM 或 Report 宣稱「全部 PASS」不影響 verdict |
| 多輪修正中刪除 assertion（W01）／改寫期望值（W03） | **延到 Phase 4**（需要 Workflow Evaluator） |

每條規則（R1–R18、R11U）都有一支「可達性測試」，斷言 `matched_rule` 等於該規則（`tests/classification/test_rules.py`）。

## Phase 2R artifact 重新分類

- 指令：`python -m evaluation.classify_runs benchmark/results/phase2r --out benchmark/results/phase3`
- 以目前的規則表離線重跑 30 個 run，只讀取 `trace.json`、`differential.json` 與 junit 報告；2R 目錄的 910 個檔案前後雜湊完全相同。
- 完整結果：[phase2r_classification.md](phase2r_classification.md)、[phase2r_classification.json](phase2r_classification.json)

### 最終（交叉驗證後）的分類分布

| layer / symptom / rule | 筆數 |
|---|---|
| SUT/ASSERTION/R11 | 8 |
| SUT/HTTP_5XX/R11 | 4 |
| AGENT/INVALID_OUTPUT/R5 | 1 |
| TEST/ASSERTION/R12 | 1 |
| TEST/CRASH/R10 | 1 |
| TEST/CRASH/R9 | 1 |

| 最終 verdict | run 數 |
|---|---|
| PASS | 13 |
| DEFECT_FOUND | 12 |
| MISSED | 2 |
| TEST_BROKEN | 2 |
| AGENT_FAILED | 1 |

### Surface（只看 pipeline）的分類分布

| layer / symptom / rule | 筆數 |
|---|---|
| SUT/ASSERTION/R11U | 9 |
| SUT/HTTP_5XX/R11U | 4 |
| AGENT/INVALID_OUTPUT/R5 | 1 |
| TEST/CRASH/R9 | 1 |

| Surface verdict | run 數 |
|---|---|
| PASS | 15 |
| DEFECT_FOUND | 13 |
| AGENT_FAILED | 1 |
| TEST_BROKEN | 1 |

UNKNOWN 分類：0 筆；INCONCLUSIVE：0 個 run。

### 與原本 verdict 的比較

**30 個 run 的 surface verdict 與最終 verdict，全部與執行當時記錄的一致，沒有任何不一致。**

重新分類的過程中發現並修正了一個症狀判斷的 bug（不影響 verdict）：

- 現象：`RUN-20260925-160630-19B8`（B03）的失敗是「期待 403、得到 200」，surface 卻被標成 `HTTP_5XX`。
- 原因：判斷 5xx 的規則只要求訊息中「有 5xx 樣式的三位數」且「有 `==`」；這筆失敗訊息附帶的任務 JSON 裡，時間戳剛好含有 `.530`。
- 修正：只在失敗的比較式本身出現 5xx 時才算（`assert 500 == 422`、`== 503`、`<Response [500`），`classification/rules.py` 與 `evaluation/differential.py` 同步修正，並把這筆訊息加為測試案例。
- 修正後 surface 的 `SUT/HTTP_5XX/R11U` 從 5 筆變成 4 筆（全部是 B04 真正的 500），`SUT/ASSERTION/R11U` 從 8 筆變成 9 筆。

### 規則在 2R 資料上實際觸發的情況

- 觸發過的規則：R5、R9、R10、R11、R11U、R12。
- 沒有觸發的規則（R1–R4、R6–R8、R13–R18）：2R 期間沒有 PROVIDER 錯誤、沒有 SUT 故障、沒有 UI 測試、也沒有權限事件，所以這些規則只由單元測試與故障注入測試驗證，尚未在真實執行資料上出現過。
