# Module: nas-schema-initialization

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
從專案 .env 連接 remote development union_db，只在已存在且沒有資料庫物件時初始化。
載入由 canonical fresh assembly 產生的 compact final schema 與 system seed，排除建庫／刪庫，不載業務 fixture。

## Implementation
- primary: `scripts/initialize_nas_schema.py`
- compact generation/load: `scripts/compact_fresh_schema.py` — 僅從自行新建的 local disposable source 產生 final DDL。
- retirement policy: `scripts/fresh_schema_policy.py`
- entrypoints:
  - `scripts/launchers/initialize_nas_schema.bat`
  - `scripts/launchers/initialize_nas_schema.sh`
- dependencies:
  - `scripts/schema_assembly.py`
  - `scripts/sql_statements.py`
  - `scripts/verify_validation_schema_manifest.py`
  - `scripts/check_runtime_database.py` — 最終 descriptor/current gate。
- config:
  - `db/fresh_schema/labor_union_fresh_current.sql`
  - `db/fresh_schema/labor_union_fresh_current.json`
  - `db/schema_assembly/labor_union_fresh_table_retirements_v1.json`
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`
  - `db/cutover_releases/labor_union_validation_schema_v1.json`

## Contracts
- owning spec: `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md#93-nas-新庫結構精簡與退役清單2026-10-15`
- compact final CREATE/seed，hash-bound source/SQL；retired tables 不進新庫，舊庫不刪表，保留物件結構與系統資料等價。
- Python／Unix 無參數唯讀預檢；Windows 無參數先預檢，通過後詢問 Y/N，僅 Y 委派 apply，結果按鍵後關閉。
- dry-run 零連線，apply fresh-read 空庫後才執行；明確命令列參數不進入互動流程。
- 同入口在寫入前唯讀檢查 MySQL/InnoDB/writable、目前帳號及啟用角色權限、binary log trigger 限制、release files 與 metadata 查詢；Apply 再驗空庫後才寫入，不另要求檢查腳本。
- 非空或 partial 重跑停止；journal 不保存 SQL、credential 或 provider exception。
- 非空拒絕時內建 readonly current 診斷，直接說明現有結構是否完整或查核失敗原因；不新增 recovery writer。
- SQL 已執行完但 object/current 驗證失敗仍 blocked；安全錯誤列 phase、完成數與 MySQL errno，保留 journal，不自動重跑。
- lock 僅協調本入口；不啟動服務，不轉換既有資料，不改 local reset／preserve-data policy。

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/nas-schema-initialization/`

## Change triggers
Reconcile when target policy, bootstrap order, failure handling, entrypoints or test roots change.
