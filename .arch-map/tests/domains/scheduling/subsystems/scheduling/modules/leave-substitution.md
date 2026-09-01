module: leave-substitution
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/leave-substitution.md
layout_status: custom_current
test_root: ui_react/src/tests/substitution_payables_readback.test.tsx

## Current oracle
- observed leave/substitution receipt triggers a case-bound Scheduling→Payroll→Staff Payables lineage readback for affected assignments。
- presentation renders only server-returned case-bound evidence and source/version subject；incomplete projection is a typed blocker, not success。
- readback failure retry only repeats typed GET and never replays leave/substitution Apply or leave-request mutation。

## Higher-boundary coverage
- `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx` — Query／Preview／Apply／receipt/re-query state machine。
- `ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx` — LINE leave inbox linkage and completion consistency。
- `tests/test_scheduling_staff_leave_review_boundary.py` — Scheduling route/application boundary。
