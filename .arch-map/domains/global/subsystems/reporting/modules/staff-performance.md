# Module: staff-performance

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
Compose monthly, quarterly and annual read-only staff performance. Credit each case and its full price once to its opening month/principal; retain each worker's own service-month hours. All trends are monthly and reconcile to period totals. Preserve unknown opening dates and prices.

## Implementation
- `subsystems/reporting/staff_performance_query.py`
- `subsystems/reporting/staff_performance_export.py`
- `infrastructure/mysql/staff_performance_query_repository.py`
- `api/schemas/staff_performance.py`
- `api/dependencies/operations_reports.py`
- `api/routes/operations_reports.py` — authenticated GET `/api/v1/operations-reports/staff-performance` and `/staff-performance/export`.
- `ui_react/src/api/reports/staff_performance_client.ts`
- `ui_react/src/components/reports/StaffPerformancePanel.tsx`
- `ui_react/src/components/reports/StaffPerformancePanel.css`
- `ui_react/src/pages/ReportsPage.tsx` — report workspace composition; existing reports remain separate.

## Dependencies
- outbound: `scheduling/schedule-generation` — effective work days and exact opening principal through rebuild/substitution lineage; no inferred actual start date or new persistence root.
- outbound: `orders/actual-start` — official actual start date and shared weekday rules for estimating historical report hours.
- outbound: `orders/historical-adoption` — adopted pairing evidence and its assignment identify the opening principal when historical orders have no effective formal work days.
- outbound: `orders/historical-service-accounting` — current confirmed service days per historical assignment.
- outbound: `orders/order-terms` — normalize registered historical service mode for the report estimate.
- outbound: `staff/staff-roster-profile` — canonical id, name and custom union number.
- outbound: `client-finance/pricing-configuration` — `case_total_amount` from complete owner pricing facts; no report-owned pricing rule.
- inbound: `staff/staff-roster-profile` — named staff performance shortcut.

## Contracts
- `document/架構重整/01_規格基線/34_營運報表與統計口徑正式規格.md` §6 STAFF-PERF-01..05, `staff-performance.v2`; XLSX includes period/ranking metadata, full-case and recognized amounts separately.
- No transaction ownership, DB writes, schema changes or external provider effects.

## Verification
- layout_status: `custom_current`
- layout_basis: Reporting tests use module roots; React mirrors the same owner in the existing Vitest runtime.
- test_root: `tests/domains/global/subsystems/reporting/modules/staff-performance/`
- test_root: `ui_react/src/tests/domains/global/subsystems/reporting/modules/staff-performance/`
- routing: `.arch-map/tests/domains/global/subsystems/reporting/modules/staff-performance.md`

## Change triggers
Reconcile when performance metrics, period, identity/price sources, read API/export, UI entry or tests change.
