module: leave-substitution
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/leave-substitution.md
layout_status: custom_current
test_root: ui_react/src/tests/substitution_payables_readback.test.tsx
test_root: ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx
test_root: tests/test_leave_substitution_public_contract.py
integration_root: tests/test_g13_leave_cancellation_disposable_mysql_e2e.py
integration_root: tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_customer_defer.py
integration_root: ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx

## Current oracle
- observed leave/substitution receipt triggers a case-bound Scheduling→Payroll→Staff Payables lineage readback for affected assignments。
- presentation renders only server-returned case-bound evidence and source/version subject；incomplete projection is a typed blocker, not success。
- readback failure retry only repeats typed GET and never replays leave/substitution Apply or leave-request mutation。

## Higher-boundary coverage
- `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx` — Query／Preview／Apply／receipt/re-query state machine。
- `ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx` — LINE leave inbox linkage and completion consistency。
- `tests/test_scheduling_staff_leave_review_boundary.py` — Scheduling route/application boundary。

- `tests/domains/scheduling/subsystems/scheduling/integration/test_leave_results_mysql.py` — 順延／代班的真實 MySQL 日期、帳務、rollback、入群與重送。
- `tests/domains/scheduling/subsystems/scheduling/integration/test_leave_results_contract.py` — 本人身分、typed transport 與退役卡片零副作用。

- `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover_mysql.py` — 工會服務中換人完整意願／邀請／入群／交接日流程、剩餘排班、實付保留、rollback 與重送。
