# Schemathesis → Agent → Hurl Workflow

狀態：`prototype-v0.4`。這是專案內可重複執行的測試 workflow 規格，不是正式業務 SSOT，也不代表已建立個人 Codex skill／plugin。

## 目標

在程式碼或 OpenAPI 變更後，以 disposable API 執行批次探索；成功案例不送入 Agent，只有經白名單化、去重與去敏的 unique failures 進入人工／Agent triage。確認的 bug 才固化成小型 Hurl regression。

## Pipeline contract

1. **Trigger**：人工在 repo root 執行 `tests/support/run_schemathesis_disposable_get.ps1`；未來可接 CI 的 code／OpenAPI change filter。
2. **Transform**：runner 只接受 `lu_test_*`，以 `APP_ENV=test`、`local_bypass` 啟動暫時 localhost FastAPI。
3. **Verification**：health contract gate → OpenAPI GET inventory → Schemathesis deterministic exploration。
4. **Refinement**：raw NDJSON 僅存於 ignored `scratch/`；filter 丟棄成功事件、合併重複／次生 failure，且只允許 operation template、check、failure type、HTTP status 與 Content-Type。
5. **Sink**：`unique_failures.ndjson` 是唯一可交給 Agent 的輸入；request values、headers、body、timestamp 與 case ID 一律不輸出。raw NDJSON 在 filter 後刪除。
6. **Triage**：Agent 只可分類為候選 `implementation_error`、`specification_error` 或 `tool_limitation`；仍須以 source／spec／focused reproduction 確認。
7. **Regression**：確認的 bug 轉成一個最小 Hurl case；固定 Hurl 8.0.1，以 `.venv/Tools/hurl/hurl.exe` 在 `lu_test_*` disposable DB 執行。
8. **Closure**：修正後重跑 focused Hurl，再重跑 Schemathesis；兩者都通過才關閉該 failure。

## 效率與 token 比較

- 每輪 `summary.json` 記錄 API readiness、Schemathesis 與完整 filter 前流程耗時。
- `context_metrics.raw_report_baseline` 代表「沒有 filter、把 raw NDJSON 當 Agent 輸入」的反事實基準；raw 本身仍不得送入 Agent。
- `context_metrics.filtered_agent_input` 代表工具處理後允許送入 Agent 的實際 artifact。
- 在沒有本機 tokenizer 與 Codex task usage API 的情況下，token 欄位採固定的 `ceil(UTF-8 bytes / 4)` 啟發式估算；同時保留精確 bytes 與 Unicode 字元數。
- 此數字只比較 artifact context，不包含 system prompt、tool call、模型輸出、cache 或帳單 token；不可宣稱為 Codex 總用量。

## Agent triage 輸出契約

- Agent 必須從 `unique_failures.ndjson` 開始，不得要求 raw request／response 作一般上下文。
- 每筆檢查結果標為 `confirmed` 或 `pending`；只有 source、正式規格或 focused reproduction 提供證據時才能 `confirmed`。
- `confirmed` classification 只能是 `implementation_error`、`specification_error` 或 `tool_limitation`。
- Triage receipt 必須記錄輸入總數、已檢查數、pending 數、reason codes、最小 evidence 與 next action；不含 request values、response body 或機密。
- 第一輪 priority triage receipt 位於同一 ignored run directory 的 `agent_triage_priority.json`；目前確認 2 筆 server errors，其他 73 筆仍為 pending，不能宣稱整批已分類。

## Failure、retry 與人工 fallback

- API、health、OpenAPI inspector 或 filter 任一失敗即 fail closed；不產生 Agent 輸入。
- 冷啟動 readiness 預設上限為 90 秒且可調；每 500 ms 探測一次，超時後不猜測、不連既有服務。
- Schemathesis 發現產品 failure 時保留非零 exit code，但仍先安全產出 unique failure artifact。
- raw NDJSON 解析不完整、超過大小上限或欄位缺失時不重試猜測；人工檢查 Schemathesis 版本與 report schema。
- 每輪 deterministic；network retry 固定為 0，避免把不穩定回應誤當成功。
- mutation、root authentication、stateful 與 Hurl conversion 仍是人工授權 gate。

## 跨專案重用

本規格與 scripts 先留在 repo，因為 disposable DB、啟動方式和 OpenAPI 邊界屬於專案。閉環穩定後，可建立個人 Codex plugin：以 skill 負責偵測專案 adapter、呼叫 workflow 並只讀取 `unique_failures.ndjson`，再以 hooks 提供流程 guardrail；CI 才是不可繞過的 hard gate。建立 plugin 仍需使用者另行明確授權。

## 專案內工具邊界

- Schemathesis 固定從 `.venv/Scripts/schemathesis.exe` 執行，不解析全域 uv tool shim。
- Hurl 固定從 `.venv/Tools/hurl/hurl.exe` 執行，不依賴 `PATH` 或系統安裝目錄。
- `.venv` 重建後必須重新安裝 Schemathesis 4.24.3 並放入 Hurl 8.0.1；未來 plugin 應提供具雜湊驗證的 bootstrap，但本階段尚未建立。
