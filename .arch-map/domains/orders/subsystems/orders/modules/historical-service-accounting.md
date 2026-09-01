# Module: historical-service-accounting

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以已採納歷史 assignment 的逐月嫂正整數服務天數，編排 Orders、Client Finance 與 Payroll 的單薪 Query／Preview／Apply；不建立逐日排班，並保留 immutable revision、receipt 與 outbox。

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
- inbound: authenticated historical-order administration only.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical day-count facts, write-once lifecycle eligibility, cross-owner versions, API/UI resource or schema changes.
