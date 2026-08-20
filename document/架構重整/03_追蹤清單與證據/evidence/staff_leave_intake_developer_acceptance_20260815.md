---
doc_type: receipt
declared_status: completed
date: 2026-08-15
owner: Scheduling
scope: Staff Leave Intake developer-local database acceptance
---

# Scheduling 月嫂請假待辦：既有本機資料庫驗收

## 結果

已在使用者明確授權下，對設定中的既有本機資料庫
`lu_test_dataset_contract_signing_v4` 執行標準 replacement flow。此名稱是專案本機設定的
union_db；不是 production 資料庫。

| Gate | 狀態 | 結果 |
|---|---|---|
| Source backup | PASS | launcher 先建立 source rollback dump。 |
| Candidate migration | PASS | candidate 套用 200、201、202 三個當前 release。 |
| Preserve-data verification | PASS | 既有資料表列數、checksum 與 primary-key fingerprint 均完成 preservation verification。 |
| Owned-object descriptor | PASS | `202_scheduling_staff_leave_intake.sql` 及所有必要 owned objects 均為 `exact`。 |
| Same-name replacement | PASS | verified candidate 已安全替換既有設定資料庫。 |
| Post-replacement current check | PASS | `scripts.update_local_database --require-current --mysql-container mysql_db` 回報 `current`。 |

## 操作證據

- source database：`lu_test_dataset_contract_signing_v4`
- candidate database：`lu_test_dataset_contract_signing_v4_local_20260815133549`
- release identity：`labor-union-staff-retirement-2026-08-15-v1`
- operator receipts（本機、含可復原 dump，未納入 Git）：
  `scratch/local_database_updates/lu_test_dataset_contract_signing_v4_local_20260815133549/`

本次沒有執行 production migration、LINE provider publish 或實機 LIFF 驗收。
