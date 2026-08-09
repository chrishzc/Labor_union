---
scope: 10_Global_保留資料Migration與Cutover_Subsystem
status: verified-local-contract
verified_at: 2026-08-09
---

# Preserve-data Migration／Cutover 重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- 核准 work package：`51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md`
- 既有 preserve-data rehearsal evidence：`evidence/preserve_data_rehearsal_*`

## 本次修復

- 公開 runner 的 `--complete-restart` 原先只有旗標，執行時固定拒絕；現在會建立
  candidate-only runtime config、啟動 release manifest 指定的 API／Streamlit／Watcher／worker
  restart ports，並依 manifest 執行 Orders、Finance Import、Scheduling、Payroll／Payables、
  Anomalies read smoke。
- complete-restart 必須明示 rehearsal API 與 Streamlit ports；ports 不得相同、必須在
  non-privileged port 範圍，startup timeout 必須為正數。
- runtime 只把 candidate descriptor 的連線資訊傳給 candidate processes；source descriptor
  不會被用作 runtime DB connection，且 password 不會進 journal／receipt payload。
- restart 或任一 smoke 失敗時，`complete_cutover_after_restart` 不寫 `completed`；switch
  receipt 保持可由 `recover-interrupted-switch` 依 before／after config digest 判斷後續行動。
- 真實 MySQL cutover gate 在未提供 `MYSQL_TEST_CONTAINER` 時改為 skipped，不再把未配置的
  外部 disposable engine 誤報為 code failure。

## 本機驗收

```text
tests/test_migrate_preserved_database_additive_schema_cli.py
tests/test_preserved_database_plan_contract.py
tests/test_preserved_database_additive_upgrade_cutover.py
tests/test_migration_release_v2_metadata.py

61 passed, 1 skipped in 1.16s

py_compile scripts/migrate_preserved_database_additive_schema.py
py_compile infrastructure/migration/rehearsal_runtime.py
passed
```

測試涵蓋 source／candidate descriptor 分權、live read-only principal 與 maintenance token、
append-only preflight/switch journal、statement resume/drift guard、atomic `.env` DB_DATABASE
switch、crash-state reconcile、rollback 不刪 candidate，以及新接入的 complete-restart runtime
boundary。未對 `.env`、`union_db`、正式主機或真實 source database 執行任何操作。

## 外部驗收界線

真實 MySQL `source → dump → new candidate → restore → additive DDL → verify → switch →
restart/read-smoke` 仍要求明確提供 disposable container、獨立 source-read/candidate-write
principals、maintenance token 與隔離 source fixture。這是規格與 work package 指定的 external
rehearsal gate；未提供該環境時 gate 會 skip，不能以 mock 或本機 unit test 取代。

## 2026-08-09 current-source verification

本次 gate 已由 `evidence/preserve_data_rehearsal_20260809/operation.json` 的 localhost
disposable MySQL 演練覆蓋：source backup digest、candidate restore／migration／verification、
switch receipt、三個 restart receipt 與 Finance Import read smoke 都為成功；演練容器與暫存
資料庫已移除。這段說明的是未提供隔離環境時的 skip 行為，不是未完成的驗收項目。

```text
preserve-data CLI / plan / cutover / release-metadata suite
63 passed, 1 skipped in 1.21s
```

唯一 skip 是未在本次 source test 命令設定 disposable MySQL container，沒有連線到正式資料庫。
