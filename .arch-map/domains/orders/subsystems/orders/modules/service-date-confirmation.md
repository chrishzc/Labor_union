# Module: service-date-confirmation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以 Query／Preview／fresh-lock Apply 保存人工確認的事前服務日期。一般案件只建立 confirmed-date root；完成 Precision Restart 且 current Scheduling generation 仍是空 tombstone 時，Query 先回傳歷史 pairing evidence 中的既定服務人員，同一 Apply 再透過 Scheduling generation replacement contract 建立 current canonical schedule；若沒有可沿用的 source assignment，仍以既定 `staff_id` 建立新 assignment，lineage 不得虛構舊 assignment identity。

## Implementation
- primary:
  - `domains/orders/service_date_confirmation.py`
  - `subsystems/orders/service_date_confirmation_workflow.py`
  - `subsystems/orders/calendar_detail_query.py`
  - `infrastructure/mysql/service_date_confirmation_repository.py`
  - `api/schemas/service_date_confirmation.py`
- entrypoints:
  - `api/routes/service_date_confirmation.py`
  - `api/dependencies/service_date_confirmation.py`
  - `api/schemas/order_calendar_detail.py`
  - `ui_react/src/adapters/orders/order_mutation_adapter.ts`
  - `ui_react/src/components/OrderServiceDatesPanel.tsx`

## Dependencies
- outbound: `scheduling/scheduling` — restart tombstone 的正式重建只呼叫 `infrastructure/mysql/scheduling_replacement_writer.py`。
- outbound: `staff-payables/payroll` — 新 assignment 在同一交易沿 source assignment frozen rate，缺少時使用既有 case payroll policy，建立 immutable assignment rate snapshot，供普通 Actual Start read model 使用。
- inbound: `orders/historical-precision-restart` — completed restart、空 effective generation 與 immutable historical pairing evidence；source assignment identity 可不存在。

## Contracts
- `GET／POST /api/v1/orders/{case_no}/service-dates` — confirmed-date Query／Preview／Apply。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1 — 一般日期確認與 restart-specific canonical Scheduling handoff。

## Verification
- layout_status: custom_current
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- static:
  - `git diff --check`
- test_root: `tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- test_root: `ui_react/src/tests/fixtures/orders/order_mutation_contract_fixtures.ts`
- higher_boundary:
  - `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/order_workbench_v2_service_dates.test.tsx`

## Provenance
- Orders owns confirmed-date Q/P/A — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。
- Scheduling owns generation replacement and `staff_schedule` — `source_observed` — `infrastructure/mysql/scheduling_replacement_writer.py`。
- Restart-specific handoff and test routes — `source_observed` — current implementation and tests listed above。

## Change triggers
- Reconcile when confirmed-date API, restart-pending detection, historical assignment lineage, Scheduling replacement contract, server read-back, or canonical test roots change.
