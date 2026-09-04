# Module: service-date-confirmation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以 Query／Preview／fresh-lock Apply 保存人工確認的事前服務日期。一般案件只建立 confirmed-date root；完成 Precision Restart 且 current Scheduling generation 仍是空 tombstone 時，同一 Apply 透過 Scheduling generation replacement contract，把可追溯的歷史 assignment 與人工日期建立為 current canonical schedule。

## Implementation
- primary:
  - `domains/orders/service_date_confirmation.py`
  - `subsystems/orders/service_date_confirmation_workflow.py`
  - `infrastructure/mysql/service_date_confirmation_repository.py`
- entrypoints:
  - `api/routes/service_date_confirmation.py`
  - `api/dependencies/service_date_confirmation.py`
  - `ui_react/src/adapters/orders/order_mutation_adapter.ts`
  - `ui_react/src/pages/OrdersPage.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — restart tombstone 的正式重建只呼叫 `infrastructure/mysql/scheduling_replacement_writer.py`。
- outbound: `staff-payables/payroll` — 新 assignment 在同一交易沿 source assignment frozen rate，缺少時使用既有 case payroll policy，建立 immutable assignment rate snapshot，供普通 Actual Start read model 使用。
- inbound: `orders/historical-precision-restart` — completed restart、空 effective generation 與 immutable historical assignment evidence。

## Contracts
- `GET／POST /api/v1/orders/{case_no}/service-dates` — confirmed-date Query／Preview／Apply。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1 — 一般日期確認與 restart-specific canonical Scheduling handoff。

## Verification
- static:
  - `git diff --check`
- test_root: `tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- higher_boundary:
  - `ui_react/src/tests/orders_service_dates_flow.test.tsx`

## Provenance
- Orders owns confirmed-date Q/P/A — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。
- Scheduling owns generation replacement and `staff_schedule` — `source_observed` — `infrastructure/mysql/scheduling_replacement_writer.py`。
- Restart-specific handoff and test routes — `source_observed` — current implementation and tests listed above。

## Change triggers
- Reconcile when confirmed-date API, restart-pending detection, historical assignment lineage, Scheduling replacement contract, server read-back, or canonical test roots change.
