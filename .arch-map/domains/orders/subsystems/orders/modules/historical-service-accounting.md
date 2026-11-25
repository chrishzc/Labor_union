# Module: historical-service-accounting

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
接受人員確認的實際服務天數，保存 immutable revision 及帳務比較快照。正式帳務差異由原帳務流程處理。
歷史多人服務歸屬透過獨立 Preview／Apply 在同一交易保存各人天數、委派 Payroll 應付及 Staff Payables 追償，並在必要時重開歷史帳務。歷史指派與天數不產生逐日班次。
費率可計算而原實付證據不足時，沿歷史天數事件及收據保存待核對，並阻擋再次結清。補齊原核銷後，沿同一 Preview／Apply 依目前天數接續帳務。

## Implementation
- primary:
  - `domains/orders/historical_service_accounting.py` — 候選要求傳入的每筆指派恰有一筆正整數天數；缺漏、重複或人員不符會拒絕。
  - `domains/orders/floor_fee.py`
  - `subsystems/orders/historical_service_accounting_workflow.py`
  - `infrastructure/mysql/historical_service_accounting_repository.py`
- entrypoints:
  - `api/routes/historical_service_accounting.py`
  - `api/dependencies/historical_service_accounting.py`
  - `api/schemas/historical_service_accounting.py`
  - `ui_react/src/components/HistoricalServiceAccountingWorkbench.tsx`
  - `ui_react/src/components/HistoricalServiceAttributionPanel.tsx`
  - `ui_react/src/api/orders/historical_service_accounting_client.ts`
- schema:
  - `db/schema_parts/215_historical_service_accounting.sql`
  - `db/schema_parts/1028_historical_service_accounting.sql`
  - `db/schema_parts/1046_client_zero_obligation_establishment.sql` — legacy schema history for zero baseline obligations.
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.json`

## 目標接線：歷史服務完成後更正

沿既有歷史服務歸屬的 Query／Preview／Apply 擴充實際起訖、時段及每日時數。以已採用的歷史指派識別為單位，由 Orders 驗證資料並委派原帳務 owner 計算差額；禁止轉呼一般班表替換或重啟。沿既有外層交易保存更正及帳務結果；待核對分支保留可獨立確認的資料，不更改已完成服務的狀態。此段是目標接線，非目前實作。驗收依[歷史服務完成後更正](../../../../../requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-completed-fact-correction)。

## Dependencies
- outbound: `client-finance/historical-service-accounting` — 計算客戶端比較金額。
- outbound: `payroll/historical-service-accounting` — 計算逐指派比較金額。
- outbound: `payroll/assignment-terms-impact` — 以歷史各人服務量建立或更正應付，保留原核銷及追償來源。
- inbound: authenticated historical-order administration（查詢／人工處理）。

## Contracts
- `.arch-map/requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical day-count revisions, completed-order eligibility, comparison inputs, API/UI resource or schema changes.
