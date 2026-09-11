# Module: staff-monthly-calendar

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
提供月嫂月份檔期的 bounded typed Query 與前端月曆投影；正式排班／占用維持主要呈現，completed legacy assignment 只形成不可操作的歷史區段。

## Implementation
- primary:
  - `subsystems/scheduling/staff_monthly_calendar_query.py`
  - `api/routes/staff_monthly_schedule.py`
  - `api/schemas/staff_monthly_schedule.py`
  - `ui_react/src/api/scheduling/staff_monthly_schedule_client.ts`
  - `ui_react/src/adapters/scheduling/historical_assignment_overlay_adapter.ts`
- entrypoints:
  - `ui_react/src/pages/SchedulingPage.tsx`
  - `ui_react/src/pages/SchedulingPage.css`

## Dependencies
- outbound: `scheduling/current-service-projection` — 正式 assignment 與 daily schedule 是 current service 的主要投影。
- outbound: `orders/operational-stage-projection` — 排查案件選項依十三核心階段的正式 current ordinal 限定在第 8「訂金」之前。
- outbound: `orders/historical-precision-restart` — precision restart event 使舊歷史指派區段失效，不得再覆蓋 restarted case。
- inbound: Scheduling UI — 只透過 typed monthly endpoint 讀取投影，不直接讀 persistence facts。

## Contracts
- `GET /api/v1/staff/{staff_id}/monthly-schedule` — `api/routes/staff_monthly_schedule.py` 與 `api/schemas/staff_monthly_schedule.py`。
- `historical_assignment` — completed legacy assignment 的唯讀 provenance projection；不宣稱 daily schedule ownership。

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/`
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/staff_monthly_schedule_client.test.ts`
- test_root: `ui_react/src/tests/scheduling_current_page.test.tsx`
- higher_boundary:
  - `tests/domains/scheduling/subsystems/scheduling/integration/`

## Provenance
- Scheduling ownership 與 typed API boundary — `architecture_declared` — repository `AGENTS.md` 與 Scheduling subsystem parent map。
- backend/API/frontend implementation paths — `source_observed` — current query、route、schema、client、adapter 與 page imports。
- 排查案件的 pre-deposit 邊界 — `source_observed` — `SchedulingPage.tsx` 讀取完整 Orders core-stage timeline，且只保留 `current_core_stage_ordinal < 8`。
- canonical Python test root — `architecture_declared` — Scheduling owner hierarchy 與 Arch Map test placement contract。
- React test paths — `source_observed` — current project colocated React test harness layout。

## Change triggers
Reconcile when monthly endpoint schema、calendar projection precedence、historical restart suppression、implementation paths或 focused test roots 改變。
