module: staff-monthly-calendar
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar.md
test_root: tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/
layout_status: custom_current
test_root: ui_react/src/tests/staff_monthly_schedule_client.test.ts
test_root: ui_react/src/tests/scheduling_current_page.test.tsx

# Owned verification
- Python owner-local coverage protects monthly projection precedence and historical restart suppression under the canonical module root.
- React client／page coverage protects strict typed decode、contiguous historical intervals、canonical-per-date precedence及唯讀 presentation。
