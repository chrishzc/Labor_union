module: staff-monthly-calendar
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar.md
test_root: tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/
layout_status: custom_current
test_root: ui_react/src/tests/staff_monthly_schedule_client.test.ts
test_root: ui_react/src/tests/scheduling_current_page.test.tsx

# Owned verification
- `test_staff_monthly_calendar_service.py` — monthly projection, unavailability, waiting locks and collision-buffer behavior using fake database responses.
- `test_staff_monthly_schedule_route.py` — monthly query validation, typed error mapping and authentication at the single-router boundary.
- `test_historical_restart_overlay.py` — historical restart suppression.
- All three Python files live under the canonical module root above; the first two were moved from the flat root without content changes on 2026-09-09.
- React client／page coverage protects strict typed decode、contiguous historical intervals、canonical-per-date precedence及唯讀 presentation。
