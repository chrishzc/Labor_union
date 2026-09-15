# Module: historical-service-accounting

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
歷史完成訂單採納時，以唯一月嫂 assignment 與 Orders 原 `service_days` 自動編排 Client Finance／Payroll 單薪基準；不要求逐筆人工輸入、不建立逐日排班。少數實際天數不同的完成訂單仍由本模組建立較新 immutable revision，並自動 rebuild 未付款月嫂應付或新增保留付款 lineage 的差額／沖正。

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
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.json`

## Dependencies
- outbound: `client-finance/historical-service-accounting` — count-based customer obligation impact.
- outbound: `payroll/historical-service-accounting` — per-assignment single-pay obligation impact.
- inbound: `orders/historical-adoption`（預設基準）及 authenticated historical-order administration（查詢／例外處理）。

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical day-count revisions, completed-order eligibility, cross-owner versions, obligation difference semantics, API/UI resource or schema changes.
