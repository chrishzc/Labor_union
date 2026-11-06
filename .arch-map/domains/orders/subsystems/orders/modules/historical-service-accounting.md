# Module: historical-service-accounting

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
接受人員確認的實際服務天數，保存 immutable revision 及帳務比較快照。正式帳務差異由原帳務流程處理。

## Implementation
- primary:
  - `domains/orders/historical_service_accounting.py`
  - `domains/orders/floor_fee.py`
  - `subsystems/orders/historical_service_accounting_workflow.py`
  - `infrastructure/mysql/historical_service_accounting_repository.py`
- entrypoints:
  - `api/routes/historical_service_accounting.py`
  - `api/dependencies/historical_service_accounting.py`
  - `api/schemas/historical_service_accounting.py`
  - `ui_react/src/components/HistoricalServiceAccountingWorkbench.tsx`
  - `ui_react/src/api/orders/historical_service_accounting_client.ts`
- schema:
  - `db/schema_parts/215_historical_service_accounting.sql`
  - `db/schema_parts/1028_historical_service_accounting.sql`
  - `db/schema_parts/1046_client_zero_obligation_establishment.sql` — legacy schema history for zero baseline obligations.
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.json`

## Dependencies
- outbound: `client-finance/historical-service-accounting` — 計算客戶端比較金額。
- outbound: `payroll/historical-service-accounting` — 計算逐指派比較金額。
- inbound: authenticated historical-order administration（查詢／人工處理）。

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical day-count revisions, completed-order eligibility, comparison inputs, API/UI resource or schema changes.
