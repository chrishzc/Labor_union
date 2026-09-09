# Subsystem: reporting

## Parent
- domain: `global`

## Responsibility
協調各owner的唯讀facts形成跨Domain營運報表；business roots與公式仍由Orders、Scheduling、Government Subsidy等owner擁有。現行runtime另接週報批次結算與指標寫入，不是整個Subsystem皆唯讀；期間與交易邊界的規格／實作差異見 `modules/weekly-operations-report.md`。

## Modules
- `weekly-operations-report` — 案件、補助與正式服務工時報表，以及現行批次寫入與期間邏輯差異；path: `modules/weekly-operations-report.md`

## Dependencies
- outbound: `orders | clients` — 查詢期間內的案件受理facts。
- outbound: `government-subsidy/reconciliation-register-query` — owner-calculated期間內補助rows。
- outbound: `scheduling` — 查詢期間內的effective正式工作日。

## Contracts
- 正式契約：自選 `start_date`／`end_date`、唯讀Query與三分頁export — `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` §15.1。
- 現行接線：`api/routes/operations_reports.py` 同時包含週報GET／export及批次POST／PATCH；這是 `source_observed`，不代表已符合上述契約。詳細entrypoints、writer與差異見 `modules/weekly-operations-report.md`。

## Verification routing
- default_boundary: Global
- module-owned verification: `modules/weekly-operations-report.md`
