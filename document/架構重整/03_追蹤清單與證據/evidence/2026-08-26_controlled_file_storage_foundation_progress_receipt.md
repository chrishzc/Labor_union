# Controlled-file storage foundation progress receipt

- Work Package：`PROV-20260826-controlled-file-storage-foundation-work-package`
- Current ID：`CUR-FILE-NAS-01`
- 驗證日期：2026-08-26
- 結論：`in-progress`；source、focused suites 與全部本機 DB change gates 已通過，enabled human Session 的
  fresh Chrome list／download 正向仍為 `NOT_RUN`。

## 實作與安全邊界

完成 typed storage port、owner-scoped metadata／version、24 小時 staging、零寫入 Preview、fresh-fact
Apply、terminal replay、list／download、cleanup、reconciliation 與 Data Center typed adapter。staging
Apply 現會重新核對持久化 owner／subject／object key／purpose／logical folder，intent mismatch 在 storage
read、owner lookup 與 outer UoW 前 fail closed。

本輪只操作 `lu_test_dataset_p0_96_empty`、`lu_test_dataset_cf_source_1003` 與
`lu_test_dataset_cf_candidate_1004`。未操作 `union_db`、production、replacement、`--switch`、正式 NAS
mount 或外部 provider。

## DB change gates

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | approved Work Package 與 `CUR-FILE-NAS-01` write set |
| Change inventory | PASS | schema-only release 1004；seed／backfill／destructive 均為 none |
| Static release | PASS | release chain、manifest、schema assembly 與 validation manifest focused tests |
| Descriptor | PASS | fresh 與 preserve candidate 對 `1004_controlled_file_storage_foundation.sql` 均為 `exact` |
| Read-only plan | PASS | `scripts.update_local_database --dry-run` 回 `status=current`、release 1004、artifact exact |
| Engine verification | PASS | MySQL 8.0.46 fresh bootstrap；1003 source dump → 1004 candidate → apply → verify |
| Developer acceptance | PASS | `lu_test_dataset_p0_96_empty` 唯讀 plan current；qualification receipt canonical-valid |

總結：`DB_CHANGE_READY`。canonical qualification 是
`validation/receipts/phase4/PROV-20260826-local-additive-qualification-controlled-file-storage-foundation.json`；
大型 dump、operation journal 與 intermediate receipts 留在 ignored `scratch/cf-qualification/`，不寫入 Git。

Preserve-data readback：source 與 candidate 的 `clients=1`、`orders=1`，owned controlled-file tables 為零列；
candidate owned object `exact`、`view_mismatches=0`。source dump SHA-256 前綴 `16a6170f`，candidate dump
SHA-256 前綴 `fe10a802`。

## Focused verification

- Python controlled-file／schema／qualification：`115 passed`。
- React controlled-file client／NAS workbench：`2 files / 15 tests passed`。
- React build：passed；只有既有 large-chunk warning。
- fresh Chrome empty-data／local-bypass：Data Center 受保護 route 回 403 typed unauthorized，未洩漏 NAS path。
- enabled human Session fresh Chrome list／download：`NOT_RUN`；不得由 unit tests 或 local-bypass 403 冒充。

## Remaining gate

只剩 enabled human Session 的 fresh Chrome 正向 list／download。正式 NAS mount、capacity／watcher 運維、
backup／restore drill、production deployment、實體搬檔、retention 與 entry switch 仍屬後續精確 target gate，
不影響本輪 DB change readiness，也不由本 receipt 授權。
