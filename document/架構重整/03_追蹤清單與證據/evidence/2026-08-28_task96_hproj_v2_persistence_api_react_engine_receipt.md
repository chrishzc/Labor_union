# Task 96 HPROJ v2 persistence／API／React／engine receipt

- `date`: 2026-08-28
- `scope`: `PKG-HPROJ-PERSISTENCE-V2` 的 additive v2 schema、persistence、typed read API、React readback 與 disposable MySQL qualification。
- `excluded`: 六 owner repair source runtime contract、正式 command runtime、真 Browser 3→2→1→0、configured developer DB replacement、另一台電腦、`union_db`、production、backfill、reset、switch。
- `result`: bounded slice `passed`；整包仍 `in-progress`，DB 總結仍為 `DB_CHANGE_NOT_READY`。

## 已完成行為

- 1014 additive successor 保存 occurrence state、active membership snapshot、delivery、checkpoint、post-commit readback 與 immutable projector receipt；原未發布1013 identity因Orders lifecycle緊急修正而機械後移。
- Receipt 另存 canonical `emitted_occurrence_identities` JSON snapshot，count／digest／逐筆 identity 可機械核對，不再只信摘要。
- Worker 將 transient persistence failure 轉為 retryable delivery，其他投影失敗進 dead letter；commit 後 mismatch 維持 `committed_unverified`。
- `HISTORICAL-BASELINE-ROOTS-001` 已進 anomaly registry；不提供 generic resolve。
- Typed read-only API 與 React Drawer readback 已接線；case number 只取 server-owned `case_no` evidence，不把 umbrella fingerprint 當案件編號。

## 驗證

- Python integrated focused：`73 passed`。
- React focused：`19 passed`；production build `passed`（只有既有 chunk size warning）。
- Fresh bootstrap：`lu_test_task96_hproj_v2_fresh_20260828_r3`，140 schema parts、377 triggers、manifest validation `passed`。
- Preserve-data：source `lu_test_task96_rpre_browser_r3_20260828` → candidate `lu_test_task96_hproj_v2_preserve_20260828_r2`，release `labor-union-historical-baseline-projector-2026-08-28-v2`，當時未發布candidate owned objects `exact`、`view_mismatches=0`、status `verified`；正式artifact identity後移為1014後由static hash與fresh bootstrap重驗。
- `git diff --check`: `passed`。

## DB gate table

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved `PKG-HPROJ-PERSISTENCE-V2`；只操作 allowlisted disposable `lu_test_*` |
| Change inventory | PASS | schema-only 1014；system seed／business backfill／destructive 均為無 |
| Static release | PASS | assembly、cutover、generated release、manifest hashes與 44 項 schema/persistence/API tests |
| Descriptor | PASS | 1014 owned objects 與 receipt JSON snapshot constraint 可區分 absent／exact／partial／drift |
| Read-only plan | PASS | ignored `scratch/task96-hproj-v2-migration/r2/plan.json`，source object `absent`、status `ready` |
| Engine verification | PASS | fresh r3 + preserve-data r2；operation status `verified` |
| Developer acceptance | NOT_RUN | 未替換 configured local DB；另一台電腦仍未驗收 |

只要 Developer acceptance 未通過，總結固定為 `DB_CHANGE_NOT_READY`。

## Current blocker

Fresh Luna/high source inventory 證明 baseline confirmed 有 durable event／receipt／outbox，但其餘六 owner 沒有共同且可唯一映射的 committed repair source contract；canonical monotonic source version 亦未定義。不得掃描 read model、用 `MAX(id)` 猜來源，或把其他用途 outbox 冒充 HPROJ trigger。需先由 Spec Pipeline 收斂 owner Apply 同一 UoW 的 typed HPROJ source emission 與版本規則，才能建立正式 command runtime 及真 Browser 3→2→1→0 驗收。
