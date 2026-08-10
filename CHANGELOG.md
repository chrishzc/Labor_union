# 變更紀錄

本檔記錄可供 reviewer 與部署負責人快速理解的版本差異。正式業務語意仍以
`document/架構重整/01_規格基線/`、release manifest 與驗收 evidence 為準。

## 2026-08-10 — 架構重整與遺留退役 Release Candidate

### 新增

- 完整 LINE identity、configuration、Rich Menu、delivery、order-group、matching、runtime
  monitoring 與 worker runtime。
- Knowledge Retrieval typed API、管理 UI、publication/review、問答與背景 worker。
- 資料庫 capability grant、authorization version、security audit retention 與 system-status UI。
- Anomaly schedule typed navigation、精確 staff lookup 與一次性配對頁導向狀態。
- Migration release v3～v9；最新 v9 納入 schema part 165 的 anomaly idempotency-key widening。
- Entry-point 與欄位權威性 evidence generator、人工裁決 queue 與 attachment review receipt。

### 修正

- IMPORT-004 在案件已寫入但告警投影失敗後，可於重跑時補送且維持冪等。
- IMPORT-006 移除 `system_alerts` 雙寫，改由 canonical anomaly workflow 處理建立、更新、
  reopen、resolve 與歷史 reprocess。
- Anomaly projector key 改為固定長度 semantic SHA-256，避免狀態往返造成重複事件鍵。
- 排班頁在服務人員不存在或不在當前分頁時 fail closed，不再導錯人或鎖住頁面。
- 智慧配對入口恢復正式 renderer，避免 radio 分支只顯示空提示。
- 修正 LINE 管理頁未定義 `_planned_panel` 所造成的 CI F821 問題。

### 退役與治理

- BreezySign provider、公開 Contract API 與 contract worker 已退役；Orders 僅保留
  provider-neutral `contract_identity` 與 contract context。
- 移除舊 Finance Alert workflow、legacy reconciliation/dispatch 與無正式 caller 的孤兒模組。
- 刪除已授權的 `fixtures/db_snapshot_v2/v3` 測試快照內容。
- 348 個正式入口全部完成裁決；九份業務附件完成 current-hash 人工語意複核。
- `system_alerts` 僅保留歷史相容資料責任，不具 mutable current-state authority。

### Schema 與部署

- Candidate schema 順序收斂至 part 165，並由 release manifest v9 與 schema gates 驗證。
- 隔離候選資料庫完成兩次 bootstrap、restart/read-smoke；已退役結構未被 schema part 或
  migration 重新建立。
- 本版本不包含任何其他部署環境的 migration／switch 授權。

### 驗證

- 完整 pytest：`1488 passed, 61 skipped`。
- Python syntax／undefined-name gate：0 findings。
- Release manifest／schema gates：30 passed。
- OpenAPI smoke：274 paths。
- 文件連結與 retirement record 檢查通過。
