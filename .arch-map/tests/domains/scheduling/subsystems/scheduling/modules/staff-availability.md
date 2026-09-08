module: staff-availability
parent_subsystem: scheduling
architecture: ../../../../../../../domains/scheduling/subsystems/scheduling/modules/staff-availability.md
layout_status: custom_current
test_root: ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/

# Owned verification
- `staff_availability_flow.test.tsx` — StaffPage 的不可服務期間查詢、Preview／Apply、readback 與不過度推論空清單。
