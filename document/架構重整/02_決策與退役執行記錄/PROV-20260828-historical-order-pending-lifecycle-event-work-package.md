# Historical Orders 待補件 lifecycle event 修正任務包

- `package_id`: `PKG-HISTORICAL-ORDER-PENDING-LIFECYCLE-EVENT`
- `package_status`: `approved`
- `specification`: `PROV-20260828-historical-order-pending-lifecycle-event-spec-gap.md`
- `owner`: Orders／Global Migration
- `authority_digest`: 2026-08-28 使用者提供另一台主機真實匯入 500 traceback並要求修復。

## 1. Scope and dependencies

- `scope`: `HOPE-R1`～`HOPE-R5`；`HOPE-A1`～`HOPE-A5`。
- `dependencies`: current Orders lifecycle／historical adoption contracts、canonical migration chain、
  `PKG-HISTORICAL-ORDER-SIX-COLUMN-STATUS`。
- `excluded`: HPROJ／RPRE／Matching、其他 anomaly repair、provider、production data、generic editor。

## 2. Work units

1. `constraint-successor`
   - 建立 additive schema part、release manifest、owned-object descriptor與migration runner exactness。
   - predecessor只接受既有缺`待補件`的精確check；unknown partial／drift固定阻擋。
2. `typed-failure-boundary`
   - 將 MySQL 3819／目標 constraint failure轉成去敏 typed 503，確認 outer UoW rollback。
3. `pending-source-regression`
   - Module／repository／API測試涵蓋`待補件→0／1／2`、replay、不同payload與未升級負向。
4. `db-and-runtime-verification`
   - Static→read-only plan→fresh bootstrap→preserve-data candidate→真 API 確認匯入。
   - fresh Luna/high獨立驗證 final candidate後，才可精確commit／push。

## 3. Write set

- 新 lifecycle constraint successor的 `db/schema_parts/`、release manifest／descriptor。
- canonical migration catalog／descriptor comparator／validation assembly與其生成 SQL。
- `api/routes/historical_order_adoption.py`。
- 直接對應tests、Orders補充規格、Task 96 ledger與final receipt。

既有其他 dirty paths必須保留且不得混入本包commit。

## 4. Completion

只有 `HOPE-A1`～`HOPE-A5`皆為`passed`、DB gate表必要項全為`PASS`、fresh Luna/high複驗通過、
文件狀態同步且 scoped commit／push完成，才把本包標為`completed`。
