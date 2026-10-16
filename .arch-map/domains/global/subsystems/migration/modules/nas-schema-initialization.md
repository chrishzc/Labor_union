# Module: nas-schema-initialization

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
從專案 .env 連接 remote development union_db，預設只初始化空庫；互動模式另提供明確確認後清空重建或建立缺少的測試庫。
載入由 canonical fresh assembly 產生的 compact final schema 與 system seed，不載業務 fixture。

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
- Python／Unix 無參數唯讀預檢；Windows 無參數委派 --interactive，空庫通過後輸入 Y 才 apply，結果按鍵後關閉。
- dry-run 零連線，--apply fresh-read 空庫後才執行；除明確 --interactive 外，命令列參數不進入互動流程。
- 同入口在寫入前唯讀檢查 MySQL/InnoDB/writable、目前帳號及啟用角色權限、binary log trigger 限制、release files 與 metadata 查詢；Apply 再驗空庫後才寫入，不另要求檢查腳本。
- 預設非空或 partial 重跑停止；journal 不保存 SQL、credential 或 provider exception。
- 非空時內建 readonly current 診斷；互動模式可選 R，完成含整庫 CREATE/DROP 權限的預檢後，顯示 host/port/database/server 並要求完整 RESET union_db 確認。
- reset 在同一 connection/session lock 中確認及重新預檢，拒絕可見的跨庫 incoming FK；確認才 journal DROP/CREATE/USE，保留 charset/collation 後共用 compact executor。取消零寫入，失敗保留現場，不自動 retry。
- reset connection read budget 600 秒（一般初始化 30 秒、connect 5 秒）；確認後只設 session lock_wait_timeout=15，逐操作 flush 進度與耗時。失敗列目前 operation／最後確認完成項；斷線不推定 DDL 成敗，不重試。
- 1049 在互動模式提供 Y/y 建庫確認，先顯示 host/port/database/server；獨立 server connection／同名 lock 先驗不存在、版本、目前帳號權限與 canonical readonly metadata 查詢，確認後再驗不存在才 CREATE/USE（無 IF NOT EXISTS、無 DROP），共用 compact executor/current gate。其他錯誤不進此分支，--apply 不自動建庫。
- SQL 已執行完但 object/current 驗證失敗仍 blocked；安全錯誤列 phase、完成數與 MySQL errno，保留 journal，不自動重跑。
- lock 僅協調本入口；不啟動服務，不轉換既有資料，不改 local reset／preserve-data policy。

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/nas-schema-initialization/`

## Change triggers
Reconcile when target policy, bootstrap order, failure handling, entrypoints or test roots change.
