# Module: historical-adoption

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將受控 historical order workbook 的可採納來源值套用到既有 Orders root，維持精確 case matching、Preview zero-write、Apply fresh recheck、replay/idempotency 與 immutable receipt/outbox；歷史來源不取得獨立 Orders authority。

## Implementation
- primary:
  - `domains/orders/historical_adoption.py`
  - `subsystems/orders/historical_adoption_workflow.py`
  - `subsystems/orders/historical_order_workbook.py`
  - `subsystems/orders/historical_order_workbook_import.py`
  - `subsystems/orders/historical_actual_start_rebuild.py`
  - `infrastructure/mysql/historical_order_adoption_repository.py`
  - `infrastructure/mysql/historical_order_workbook_import_repository.py`
  - `infrastructure/mysql/historical_order_adoption_cancellation_decorator.py`
  - `infrastructure/mysql/historical_actual_start_date_planner.py`
  - `scripts/diagnose_historical_order_preview.py` — read-only source-schedule conflict and scheduling-root diagnosis.
- entrypoints:
  - `api/routes/historical_order_adoption.py`
  - `api/dependencies/historical_order_adoption.py`
  - `api/schemas/historical_order_adoption.py`
  - `scripts/imports/adopt_historical_orders.py` — operational use remains subject to entry-point governance.
- migrations:
  - `db/schema_parts/1008_historical_order_adoption_noop_constraint.sql`
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql`
  - `db/schema_parts/1027_historical_order_pairing_resolution_reused.sql` — preserve-data successor.
  - `db/migration_releases/labor_union_2026_08_27_historical_order_adoption_noop_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json`

## Dependencies
- outbound: `anomalies/anomalies` — committed review evidence can be projected by `subsystems/anomalies/historical_order_adoption_outbox_consumer.py`.
- outbound: `orders/actual-start` — deposit-paid historical rows whose source date differs from the HCM planned start rebuild current official service facts through the canonical writer in the same outer UoW; source status `1` alone never triggers this path.
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
