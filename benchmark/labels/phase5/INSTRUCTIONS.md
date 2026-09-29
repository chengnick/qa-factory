# 人工標註說明（Phase 5 歸因準確率，spec v3 §11.2）

標註檔：`sheet.csv`（40 筆）。每一列是一個被分類器歸因過的失敗。
**標註完成之前，不要打開 `sheet_key.csv` 與 `key.json`**：前者是從表中拿掉的交叉驗證欄位，後者是分類器的答案。

用 Excel 或任何編輯器填寫，存檔時保持 UTF-8 CSV（Excel：「CSV UTF-8」）。只填 `human_layer`、`targets_injected_bug`、`notes` 三欄，
其他欄位不要修改。

## 1. `human_layer`（必填）

依 spec v3 §5.1，填以下其中一個值：

| 值 | 定義 |
|---|---|
| `SUT` | 被測系統行為不符需求（= 找到 bug） |
| `TEST` | 產生的測試程式本身有錯 |
| `HARNESS` | 工具封裝或執行框架出錯（包括 LLM API 拒絕請求） |
| `AGENT` | 模型行為錯誤：輸出格式錯、呼叫不存在的工具、參數錯、handoff 缺欄位 |
| `PROVIDER` | LLM 服務不可用：429、5xx、API timeout、連線失敗 |
| `ENV` | 本地環境問題：SUT 未啟動、埠衝突、瀏覽器無法啟動 |
| `UNKNOWN` | 無法判定 |

## 2. `targets_injected_bug`

`yes` / `no` / `n.a.`：這支測試失敗，是否因為它確實測到了 `sut_bugs` 所列的 bug。

- `sut_bugs` 是 `(clean)` 的列，或 `kind` 不是 `diff` 的列（`llm`、`agent`）：填 `n.a.`。
- 其餘的列（`kind = diff` 且有開 bug）：讀 `test_id` 那支測試的程式碼和錯誤訊息，對照 `bugs.yaml` 對這個 bug 的描述。
  - 測試檢查的正是這個 bug 造成的錯誤行為，失敗的斷言也對應到它 → `yes`
  - 測試失敗的原因與這個 bug 無關（例如測試本身寫錯、測的是別的規則、剛好被其他行為連帶影響） → `no`
  - 看不出來 → 不要硬選：留空，並在 `notes` 說明原因（計分時算作「無法判斷」，另外列出）

## 3. 可以參考的資料

- 產生的測試程式：`generated_tests` 欄的路徑，相對於 `benchmark/results/phase5/`
  （例如 `RUN-…/generated/test_req004_ui.py`）；`test_id` 指出是哪一支測試
- 需求文件：`benchmark/requirements/<requirement_id>.md`
- API 說明：`docs/sut-api.md`
- Bug 說明：`benchmark/bugs.yaml`（`sut_bugs` 欄列出這次開的 bug；`(clean)` 表示沒有開）
- `observation`：原始錯誤訊息（已移除規則編號與交叉驗證的前綴）

## 4. 規格模糊或無法判斷時

在 `notes` 寫明原因（例如「需求沒規定非數字 id 要回 404 還是 422」），不要硬選一個值。
`human_layer` 無法判斷時填 `UNKNOWN`；`notes` 可以寫你傾向的答案與理由。

## 5. 抽樣方式

- 母體：`benchmark/results/phase5` 中 84 筆被分類的失敗（90 個 run 的 `classification.json`），
  依分類器的 layer：AGENT 1, PROVIDER 24, SUT 37, TEST 22。
- 分層抽樣 40 筆：每個 layer 至少 3 筆（不足則全取），其餘名額依各 layer 大小按比例分配（D'Hondt），
  各層內以 seed `20260928` 隨機選取。結果：AGENT 1, PROVIDER 11, SUT 18, TEST 10；
  依類型：agent 1, diff 28, llm 11。
- 列的順序以 seed `20260929` 隨機打亂，與 run、類型、layer 無關。
- 樣本的 layer 比例接近母體（各 layer 的母體與樣本筆數見上）；準確率依類型分開報告（見下節）。

## 6. 準確率怎麼算

完成後執行 `python -m evaluation.labels score --out benchmark/labels/phase5`。它先檢查每一列都已填、值都合法，然後：

- **主要數字：只用 `kind = diff` 的列**（產生的測試在交叉驗證中的失敗），計算 `human_layer` 與分類器 layer 一致的比例，附 Wilson 95% 信賴區間。
- `llm` 與 `agent` 類型的列另外報告（它們的歸因主要看例外類型，幾乎沒有判斷空間），不併入主要數字。
- `human_layer = UNKNOWN` 的列計為不一致，並另外列出筆數。
- `targets_injected_bug`：在有開 bug 的 diff 列中，分別統計 `yes` / `no` / 留空（無法判斷）的筆數，並對照分類器判為 `SUT` 的列。
  留空只在 `notes` 有寫原因時才接受；`n.a.` 的列必須填 `n.a.`。
- 產出 `score.json` 與 `score.md`，列出每一筆不一致的 id。
