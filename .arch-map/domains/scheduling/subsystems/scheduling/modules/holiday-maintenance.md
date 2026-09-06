# Module: holiday-maintenance

## Parent
- domain: scheduling
- subsystem: scheduling

## Responsibility
將官方單一年度國定假日 CSV 轉成 typed rows，經既有 Scheduling owner 的逐筆 Query／Preview／Apply 維護 holiday facts；Preview 必須零寫入，Apply 必須以每筆 fresh calendar version 並保留既有 owner facts。

## Implementation
- primary owner: subsystems/scheduling/holiday_maintenance.py
- typed client: ui_react/src/api/scheduling/holiday_client.ts
- presentation: ui_react/src/pages/SchedulingPage.tsx

## Contracts
- GET /api/v1/holidays
- POST /api/v1/holidays/preview
- POST /api/v1/holidays/apply
- official CSV fields: 西元日期、星期、是否放假、備註；0 表示上班，2 表示放假。

## Verification
- layout_status: custom_current
- tests: see the holiday-maintenance test module leaf.
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/`
- boundary: Subsystem
- oracles: actual parser, transport call order, zero-write Preview, fresh per-date Apply version, preserve/skip/partial failure, awaited UI readback failure, and adapter state/retry transitions.

## Provenance
- owner and workflow: source_observed from subsystems/scheduling/holiday_maintenance.py and current typed client.
- frontend presentation: source_observed from SchedulingPage.tsx.
- canonical test placement: architecture_declared by the existing Scheduling Holiday module test root and current test routing.
