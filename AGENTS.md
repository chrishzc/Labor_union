# Workspace Agent Rules

本檔案是本專案所有 AI Agent 與自動化程式修改工作的根層規範。
本專案不使用 ADAD Task、Checkpoint、Source Lock、system map gate 或 ADAD 工具。

## 1. 業務與架構優先

- 思考程式、資料與流程時，先以實際業務場景和第一性原理拆解問題。
- production code 與 pytest 開始前，必須先完成並取得人工確認的整體
  `Global → Domain → Subsystem → Module` 架構。
- 架構必須明確記錄各層責任、SSOT、根事實、衍生值、狀態機、交易邊界、
  typed errors、idempotency、retry、conflict handling、異常警示與人工操作入口。
- 規格文件與人工已確認決策是業務語意依據；live schema、API、Service、SQL writer
  與 production caller 是現況證據。兩者有漂移時必須明確揭露，不得把現況誤當規格。
- legacy `system_map*.md`／`system_map*.yaml` 僅供歷史參考，不是 SSOT、授權或 gate。

## 2. 分層實作與驗證

- 架構完整確認後，才可以依獨立 Source 範圍平行撰寫 production code 與測試。
- Module 驗證局部 input、output、invariant、exception 與 dependency。
- Subsystem 驗證 Module 編排、資料形狀、狀態機、交易、replay、partial failure、
  stale 與 conflict 等完整業務場景。
- Domain 驗證該領域從根事實到最終結果的端到端運作。
- Global 驗證跨 Domain 不變量與 release 主流程。
- 測試失敗時，以失敗所屬層級作為整體修正單位；不得只修到單一 assertion 通過，
  卻破壞同層契約或跨層不變量。
- Streamlit 是可替換薄顯示層，只能呼叫後端 API 並顯示 typed results；
  業務規則只能存在 Server／Service 層。
- 新增或修改 UI API client 時，client 必須對應單一 bounded domain；跨 Domain 的
  endpoint 不得附加到既有 Domain client。需要共用認證時，以明確的 shared transport
  composition 處理。
- UI API client 邊界必須將成功 payload 驗證為 Pydantic view 或其他 typed result，並將
  transport／schema 錯誤轉成 typed client error；不得讓未驗證的 raw `dict` 穿透到 UI
  render function。

## 3. Dirty worktree 保護

- 開始前 fresh-read branch、HEAD、status 與相關檔案。
- 既有未提交修改都視為使用者成果。不得 reset、clean、stash、切換分支、建立 worktree、
  覆蓋或刪除無關 dirty paths。
- 修改範圍只限本次任務直接需要的檔案；遇到重疊修改時先辨認來源與語意再動手。
- `fixtures/db_snapshot_v2/v3` 是測試假資料快照；除非使用者明確指定，不得刪除或整理。
- 不得自行 commit、stage、push 或建立 PR，除非使用者明確要求。

## 4. AI Agent Clean Code 守則

每次生成或修改程式碼時，依序執行：

`寫程式碼 → 自我檢查 Rule 1～5 → 發現違反就自行修正 → 交付`

任何一條沒有把握時，先拆解或重寫，不交付不合格程式碼。

### Rule 1：3 秒命名

- 名稱必須精準表達用途，讓第一次看到的人在 3 秒內猜到意圖。
- 禁止魔術數字、模糊縮寫與無意義編號，例如 `d`、`data1`、`userList2`。
- 變數使用具體名詞，例如 `elapsed_time_in_days`、`unpaid_invoices`。
- 函式使用動詞短語，例如 `calculate_tax()`；類別使用名詞，例如
  `InvoiceCalculator`。
- 收尾時重讀所有新增或修改的名稱；無法在 3 秒內理解就改名。

### Rule 2：20 行樂高積木

- 單一函式以 20 行為預設上限，並維持單一職責與單一抽象層。
- 不得在同一函式混合讀 API、解析資料、寫資料庫等不同責任。
- 高層業務流程不得與底層字串或序列化細節混在同一函式。
- 超過 20 行時先嘗試拆成可理解的小單元。
- 若拆分會產生更難懂的間接層，允許保留超過 20 行，但必須在函式上方用一行註解
  說明「為何不拆分」。

### Rule 3：防禦型單向出口

- 優先使用 guard clauses；異常與邊界情況先 return 或 throw，再進入主流程。
- 儘量避免不必要的 `else`；若兩邊都是同等重要的正常分支，可以使用 `else`。
- 縮排以 2 層為預設上限；超過時優先抽出職責函式，不以放寬限制掩蓋複雜度。

### Rule 4：程式即文件

- 用名稱、型別、物件與函式本身表達意圖。
- 禁止複述程式行為的註解，例如「宣告變數」或「呼叫 API」。
- 註解只用來解釋無法從程式本身看出的 Why，例如特殊業務考量或暫時繞過已知問題；
  不寫 What 或 How。

### Rule 5：童軍營地法則

- 只修改與本次任務直接相關的程式碼。
- 修改某個函式或檔案時，可以清理該邊界內明顯的壞命名或重複邏輯。
- 禁止跨模組、跨檔案的順便重構，不擅自改動無關邏輯。
- 交付前逐行確認：每一行改動都能對應本次任務；說不出理由的改動必須還原。

## 5. 文字、測試與協作

- 所有文字檔使用 strict UTF-8，預設無 BOM；不得用 replacement 或 ignore 隱藏解碼錯誤。
- Python 測試使用專案 `.venv\Scripts\python.exe -m pytest`，指定有限 timeout。
- 每一個 production、script 或 test 的直接第三方 import，都必須在 `pyproject.toml`
  的 `dependencies` 或適當的 dependency group 明確聲明；不得依賴 transitive package
  恰好存在。變更相依後必須同步更新 `uv.lock`，並以 `pytest -W error` 驗證。
- 測試資料、正式資料庫與外部服務必須明確隔離；不得把測試操作套用到正式資料。
- 只有兩個以上互不依賴、寫入範圍不重疊且交接成本合理的工作才平行派工。
- 子代理不得擴大範圍、修改共享檔案或自行 commit；主代理負責整合與最終自我檢查。
