# Module: official-service-date-correction

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
完成案件正式服務日期的 Query／Preview／fresh-lock Apply。完整更正日期由 current effective Scheduling 取得，date-only 更正於同一 outer transaction 委派 Scheduling generation replacement、保留不可變 Orders lifecycle 更正證據與既有 service-data lock；不重建金額義務。金額影響無法安全承接時 fail closed。

## Implementation
- primary:
  - `subsystems/orders/official_service_date_correction_workflow.py`
  - `infrastructure/mysql/official_service_date_correction_repository.py`
- entrypoints:
  - `api/routes/official_service_date_correction.py`
  - `api/dependencies/official_service_date_correction.py`
  - `ui_react/src/api/orders/official_service_date_correction_client.ts`
  - `ui_react/src/components/OrderOfficialDateCorrectionPanel.tsx`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Dependencies
- outbound: `scheduling/schedule-generation` — `infrastructure/mysql/scheduling_replacement_writer.py` 為唯一正式排班世代更換 writer。
- outbound: `global/reporting/weekly-operations-report` — 週報重新查詢直接讀 effective `staff_schedule`，不另建同步投影。
- outbound: `payroll/assignment-terms-impact` — 薪資率 snapshot 只按 immutable source carry；特殊薪資、調整等金額影響 fail closed。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.3、Issue #346。
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` §7。

## Verification
- layout_status: custom_current
- React tests follow the existing frontend module layout; backend tests use the Module root.
- test_root: `tests/domains/orders/subsystems/orders/modules/official-service-date-correction/`
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/official-service-date-correction/`
- static: `git diff --check`

## Provenance
- Orders correction lineage and Scheduling ownership — `requirement_declared` — Issue #346 and current Orders/Scheduling formal specs.
- Effective readback and fresh Weekly Report — `source_observed` — current Scheduling writer and weekly report query adapter.

## Change triggers
Reconcile when correction entrypoint, generation replacement, payroll source carry, lifecycle evidence, effective schedule query, or focused integration root changes.
