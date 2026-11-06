# Module: historical-adoption-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以 strict typed API schema 與 adapter 呈現 Historical Orders Preview／Apply 結果；needs-review receipt 僅傳回既有 review identity，讓 composition 開啟既有更正工作台。狀態統計由 server 擁有，前端不得重算或取得 Orders mutation authority。

## Implementation
- primary:
  - `ui_react/src/api/orders/historical_order_workbook/`
  - `ui_react/src/adapters/orders/historical_order_workbook_adapter.ts`

## Dependencies
- inbound: `orders/orders/module:historical-adoption` — 消費 typed preview／receipt contract。
- outbound: `global/application-shell/module:data-import-composition` — 提供 Data Import page 可組成的 typed client／adapter 與 review reference。

## Contracts
- Historical source-schedule conflict errors retain only the existing typed `field_errors` (field/code/message) as `fieldErrors` for Preview and Apply; partial-import receipts carry structured `historical_order_source_schedule_conflict_detail:*` row issue codes without exposing client PII or normal accounting details.
- CHECK 3819 提供狀態、收據一致性、配對關聯的封閉說明與安全規則代碼；保留原命令人工查詢，不自動重送。
- Preview／Apply 顯示 `historical_order_database_*` 的封閉原因與 MySQL 數字，保留舊通用錯誤碼支援；Apply 維持同命令結果未確認與人工查詢，資料庫資料鎖／死結不自動重送。
- 當次 `import_counts` 投影成功寫入、資料已一致與未匯入，另顯示檔外取消筆數。主動重匯建立新操作，結果未知時提示查核正式訂單與異動紀錄，不自動重送。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.7 — Historical Order Adoption。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_order_workbook_client.test.ts`

## Provenance
- Presentation 不重算 owner facts — `architecture_declared` — Orders historical adoption contract。
- React client／adapter 路徑 — `source_observed` — current repository。

## Change triggers
Reconcile when typed API schema、client、adapter、status counts 或 presentation test path changes。
