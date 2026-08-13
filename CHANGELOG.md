# 變更紀錄

本檔記錄可供 reviewer 與部署負責人快速理解的版本差異。正式業務語意仍以
`document/架構重整/01_規格基線/`、release manifest 與驗收 evidence 為準。

## 2026-08-13 — 開發者本機資料庫維護與啟動腳本收斂

### 新增

- 新增 `scripts/update_local_database.py` 與
  `scripts/launchers/update_local_database.bat`：先備份 source、建立 candidate、依 versioned
  migration／backfill 升級並驗證，通過 source-stale guard 後才同名替換 `union_db`；最終驗證失敗
  時使用原始 dump 嘗試 rollback。
- 所有專案 operator-facing launcher 集中到 `scripts/launchers/`，用途、安全邊界、替代與退役對照
  統一記錄在該目錄的 `README.md`。
- 現行 launcher 提供零副作用 dry run：Batch／shell／Python 使用 `--dry-run`，PowerShell 使用
  `-DryRun`；只驗證路徑、module 與 executable，不啟動服務、不改 `.env`、DB 或排程任務。
- 新增 release 188：月嫂配對偏好定義／值與長假、暫停接案資料，由 typed API 與管理 UI 維護，
  配對中心與 Calendar 讀取同一份 current facts。
- HCM 日常匯入採 authenticated Web upload；Client／Staff BeClass scripts 改為受限 historical
  import lane，避免一般 Web UI 或 File Watcher 旁路寫入 current profile。

### 修正

- 提供開發者更新 `main` 後的正式本機 DB 升級入口，避免程式已引用新 table／view、但本機 schema
  仍停在舊版而造成 API 500、runtime heartbeat 或 outbox worker 缺表。
- 保留「保留現有資料升級」與「捨棄資料載入模板」兩條不同契約，`reset_DB.bat` 不再被誤當成
  update workflow 的相容別名。
- 修正 Windows Batch dry-run 在括號區塊內未正確傳遞 `%ERRORLEVEL%`，blocked preflight 現在會
  回傳非零 exit code。
- 新增 Windows `--smoke-test`：實際等待 MySQL、啟動 API／UI／monitor／file watcher／durable
  worker、驗證 health 後清理本次 PID。LINE worker 缺少有效本機憑證時改為明確 skipped，不再開啟
  立即失敗的程序視窗。
- MySQL release chain 納入 WP72 artifact 188，並補強 preserved-data migration 在 `TIME` 欄位的
  canonical fingerprint 表示，避免備份副本升級時因 Python 時間型別造成 verifier 失敗。

### 搬移與退役

- `online.bat`／`online.sh` 改為 `scripts/launchers/start_local_development.*`；重複 alias
  `start.bat` 退役。
- `dev_API.bat` 改為明確的 `start_local_development_no_auth.bat`；Admin no-auth 設定入口同步搬移
  並改名。
- Durable Job Worker 主機 supervision 仍依人工裁決暫緩，因此 installer 退役；既有排程只保留
  recovery-only status／uninstall 入口。
- `start_fastapi_ngrok.py` 搬入 launcher 目錄，仍明確限制為 development-only。

### 已知限制與驗證

- 模板 reset 的 canonical 入口已保留，但版本庫目前沒有
  `fixtures/db_snapshot_v2/v3/manifest.json`；依人工裁決 fixture 重建另案處理，因此 preflight 會
  fail closed，不會刪除 DB。
- ngrok launcher 需要另外安裝 `ngrok`；Unix launcher 需要 `lsof`。缺少依賴時 dry run 回傳
  `blocked`，不會嘗試安裝或啟動。
- WP74 兩方向真實 MySQL 驗收已通過：空 schema 套用欄位／資料表升級，以及目前 DB 完整備份副本
  還原後升級與資料保存。WP75 Windows launcher smoke 已通過；API 與 Streamlit health 為 200，所有
  本次建立的應用程序與 8000／8501 監聽均已清理。模板 fixture reset 依人工裁決不在本次範圍。

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
