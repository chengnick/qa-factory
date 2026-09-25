# Phase 2R 驗收紀錄：開發集 5 輪

- 日期：2026-09-25（UTC 16:05–16:28）
- 指令：`python -m evaluation.run --dataset dev --rounds 5 --llm gemini --model gemini-3.5-flash-lite --pause-s 10 --results-dir benchmark/results/phase2r`
- 程式版本：commit `32c5e1e`（Phase 2R 程式碼）。30 個 run 的 `meta.json` 都記錄這個 commit
- 模型：`gemini-3.5-flash-lite`，temperature 0；30 個 run 的服務方回報版本都是 `gemini-3.5-flash-lite`
- Prompt 版本：`v3`（未修改；`tests/agents/test_prompt_version.py` 以 hash 鎖定）
- lockfile sha256：`e727f4d1a5cfe7854fa25fe3b625d58cf7cfa6ab70c40f891ddaa2d674326cd6`
- 範圍：只有開發集（B02、B03、B04）與這 3 個需求的乾淨版；測試集未執行
- 每個 run 的完整 artifact 都在本目錄 `RUN-*/`（30 個，全部通過秘密掃描）；逐 run 明細也見 [summary.md](summary.md)

## 指標（spec v3 §11.2）

| 指標 | 數值 |
|---|---|
| 真實偵測率（交叉驗證） | 80%（範圍 67%–100%，輪數 n=5，合計 12/15） |
| 表面偵測率（未交叉驗證） | 80%（範圍 67%–100%，輪數 n=5，合計 12/15） |
| **誤報率（surface，主要數字）** | 7%（範圍 0%–33%，輪數 n=5，合計 1/15） |
| 誤報率（交叉驗證後；依定義為 0） | 0%（範圍 0%–0%，輪數 n=5，合計 0/15） |
| 測試健康度 | 98%（範圍 94%–100%，輪數 n=5，合計 101/103） |
| 環境阻擋率 | 0%（範圍 0%–0%，輪數 n=5，合計 0/30） |

- 平均值與範圍以「每輪的比率」計算；「合計」是全部 run 加總。
- 環境阻擋（ENV_BLOCKED）的 run 不計入其他指標的分母；本次 0 次。
- AGENT_FAILED 的 run 計入分母、視為未抓到（B04 第 4 輪）。

### 每個 bug 的偵測率

| Bug | 交叉驗證 | Surface | 環境阻擋 |
|---|---|---|---|
| B02 | 3/5 | 3/5 | 0/5 |
| B03 | 5/5 | 5/5 | 0/5 |
| B04 | 4/5 | 4/5 | 0/5 |

## 為什麼誤報率以 surface 為主要數字

實際使用時沒有乾淨版可以比對，使用者看到的就是 surface verdict，所以 surface 誤報率才是使用者實際會遇到的誤報。

乾淨版的 run 在交叉驗證時兩個 build 都是乾淨版：失敗的測試只會落入 R12 或 R13（測試壞了），不可能落入 R11（抓到 bug）。因此交叉驗證後的誤報率依定義一定是 0，只列出作為對照。

## 交叉驗證這次改變了什麼

- **開 bug 的 run**：真實偵測率與表面偵測率相同（12/15）。這 15 次中沒有「碰巧失敗被當成偵測」的情況，交叉驗證確認了 12 次偵測都與 bug 開關有關。
- **乾淨版的 run**：1 次 surface 誤報（`RUN-20260925-162242-4188`）被交叉驗證判為 R12，也就是測試本身錯誤。

## 全部 30 個 run

| 輪 | run_id | 需求 | Bug | Surface | 交叉驗證後 | 抓到 / 壞掉 / 測試數 | 說明 |
|---|---|---|---|---|---|---|---|
| 1 | `RUN-20260925-160546-73BF` | REQ-005 | B02 | PASS | MISSED | 0 / 0 / 6 | 漏抓：「done 是終態」只測了 done→todo，沒測 done→in_progress |
| 1 | `RUN-20260925-160630-19B8` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 1 | `RUN-20260925-160714-7485` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 1 | `RUN-20260925-160754-1661` | REQ-005 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 1 | `RUN-20260925-160844-FFB7` | REQ-007 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |
| 1 | `RUN-20260925-160935-E01D` | REQ-002 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 2 | `RUN-20260925-161022-8C22` | REQ-005 | B02 | PASS | MISSED | 0 / 0 / 5 | 漏抓：同上 |
| 2 | `RUN-20260925-161132-894F` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 2 | `RUN-20260925-161217-D84D` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 2 | `RUN-20260925-161300-9E1B` | REQ-005 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 2 | `RUN-20260925-161347-60D6` | REQ-007 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |
| 2 | `RUN-20260925-161448-162F` | REQ-002 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 3 | `RUN-20260925-161532-CAA1` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 4 |  |
| 3 | `RUN-20260925-161615-9CE6` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 3 | `RUN-20260925-161703-D276` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 4 |  |
| 3 | `RUN-20260925-161747-CF2A` | REQ-005 | （乾淨版） | TEST_BROKEN | TEST_BROKEN | 0 / 1 / 1 | 產生的測試檔無法收集（collection failure），兩個 build 都是 ERROR（R10）；surface 也是 TEST_BROKEN，不算誤報 |
| 3 | `RUN-20260925-161823-0279` | REQ-007 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |
| 3 | `RUN-20260925-161907-808D` | REQ-002 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 4 | `RUN-20260925-161951-52A1` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 5 |  |
| 4 | `RUN-20260925-162051-4B53` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 4 | `RUN-20260925-162140-FD00` | REQ-002 | B04 | AGENT_FAILED | AGENT_FAILED | - | Automation 輸出的 JSON 不合法（line 16 col 7），pipeline 中止；非 PROVIDER，計入分母 |
| 4 | `RUN-20260925-162200-4DA6` | REQ-005 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 4 | `RUN-20260925-162242-4188` | REQ-007 | （乾淨版） | DEFECT_FOUND | TEST_BROKEN | 0 / 1 / 3 | surface 誤報：測試用非數字 ID 查詢並期待 404，SUT 回 422；交叉驗證判為 R12（兩邊都失敗）→ TEST_BROKEN |
| 4 | `RUN-20260925-162323-26D9` | REQ-002 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |
| 5 | `RUN-20260925-162403-2580` | REQ-005 | B02 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 4 |  |
| 5 | `RUN-20260925-162445-0518` | REQ-007 | B03 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 3 |  |
| 5 | `RUN-20260925-162526-8372` | REQ-002 | B04 | DEFECT_FOUND | DEFECT_FOUND | 1 / 0 / 4 |  |
| 5 | `RUN-20260925-162609-DB83` | REQ-005 | （乾淨版） | PASS | PASS | 0 / 0 / 4 |  |
| 5 | `RUN-20260925-162650-B731` | REQ-007 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |
| 5 | `RUN-20260925-162731-E98A` | REQ-002 | （乾淨版） | PASS | PASS | 0 / 0 / 3 |  |

## 已知問題與限制

- **`git_commit.dirty` 標記有誤**：只有第 1 個 run 記為 `dirty: false`，其餘 29 個與 summary 都是 `true`。原因是執行器每跑完一個 run 就把它複製進 `benchmark/results/phase2r/`，這些尚未追蹤的新檔案讓工作目錄變成 dirty。已確認 30 個 run 的 commit 都是 `32c5e1e`，與這個 commit 相比，被追蹤的檔案沒有任何變更。修正方式（尚未實作）：判斷 dirty 時排除結果目錄，或先寫到 `artifacts/` 最後再一次複製。
- **B02 的漏抓是 prompt 層面的問題**：兩次都只測 `done → todo`。依 Phase 2R 規則沒有修改 prompt。
- **只有 5 輪、每個組合 n=5**，比率的解析度是 20%。
- **交叉驗證的限制**（spec v3 §6.4）：只能確認失敗與 bug 開關有關，不能確認測試描述的就是那個 bug。
