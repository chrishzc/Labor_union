# Module: historical-adoption

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將受控、單一月嫂 historical order workbook 的可採納來源值套用到既有 Orders root，維持精確 case matching、Preview zero-write、Apply fresh recheck、replay/idempotency 與 immutable receipt/outbox；歷史完成訂單在同一 outer UoW 依 Orders 原 `service_days × service_hours_per_day` 自動建立基準帳務，不猜測逐日排假。

## Implementation
- primary:
  - `domains/orders/historical_adoption.py`
  - `subsystems/orders/historical_adoption_workflow.py`
  - `subsystems/orders/historical_order_workbook.py`
  - `subsystems/orders/historical_order_workbook_import.py`
  - `subsystems/orders/historical_order_adoption_outbox_consumer.py`
  - `subsystems/orders/historical_actual_start_rebuild.py`
  - `infrastructure/mysql/historical_order_adoption_repository.py`
  - `infrastructure/mysql/historical_order_workbook_import_repository.py`
  - `infrastructure/mysql/historical_order_adoption_cancellation_decorator.py`
  - `infrastructure/mysql/historical_actual_start_date_planner.py`
- entrypoints:
  - `api/routes/historical_order_adoption.py`
  - `api/dependencies/historical_order_adoption.py`
  - `api/dependencies/historical_order_review_remediation.py`
  - `api/schemas/historical_order_adoption.py`
  - `scripts/imports/adopt_historical_orders.py` — operational use remains subject to entry-point governance.
- migrations:
  - `db/schema_parts/1008_historical_order_adoption_noop_constraint.sql`
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql`
  - `db/schema_parts/1027_historical_order_pairing_resolution_reused.sql` — preserve-data successor.
  - `db/migration_releases/labor_union_2026_08_27_historical_order_adoption_noop_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json`

## Dependencies
- outbound: `scheduling/matching-coordination` — discussion＋開始日空白＋唯一月嫂來源透過 typed borrowed-transaction port 建立正式 proposed Matching plan；其他來源不得製造 Matching root。
- outbound: `anomalies/anomalies` — committed review evidence由 `subsystems/orders/historical_order_adoption_outbox_consumer.py`確認投遞；歷史服務日曆未確認維持 owner review，不建立推測帳務。
- outbound: `orders/historical-service-accounting`、`payroll/historical-service-accounting`、`client-finance/historical-service-accounting` — 歷史完成訂單採納時使用唯一月嫂與 Orders 原服務天數，在同一 outer UoW 建立基準帳務；不建立逐日服務日。
- outbound: `orders/service-date-confirmation` — 只有歷史未服務／服務中案件明確重啟後，才由正常流程建立正式服務日；歷史完成訂單的天數修正留在 `orders/historical-service-accounting`。
- inbound: Case Import / operator import entry — only through typed source/workflow boundary.

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — historical adoption semantics and Orders ownership.
- `document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md` — script/API entry lifecycle.

## Verification
- static:
  - `db/schema_parts/1008_historical_order_adoption_noop_constraint.sql`
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql`
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-adoption/`

## Provenance
- Orders ownership and historical adoption contract — `architecture_declared` — `01_Orders_Domain.md`.
- API/repository/migration paths — `source_observed` — current repository.
- Owner-local test routing — `source_observed` — module-owned unit/contract/regression roots.

## Change triggers
Reconcile when historical workbook contract, Orders owner, API/script entry, persistence schema, receipt/replay semantics or test roots move.
