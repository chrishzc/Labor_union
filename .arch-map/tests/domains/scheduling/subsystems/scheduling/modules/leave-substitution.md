module: leave-substitution
parent_subsystem: scheduling
architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/leave-substitution.md
layout_status: custom_current
test_root: ui_react/src/tests/substitution_payables_readback.test.tsx
test_root: ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx
test_root: ui_react/src/tests/leave_substitution_client.test.ts
test_root: tests/test_leave_substitution_public_contract.py
integration_root: tests/test_g13_leave_cancellation_disposable_mysql_e2e.py
integration_root: tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_customer_defer.py
integration_root: ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx

## Current oracle
- 歷史代班收據的 Scheduling → Payroll → Staff Payables 血緣依案件與操作鍵唯讀查詢。
- 唯讀應付款查詢保留來源證據與版本。不完整投影保留具體擋關原因。
- 讀取失敗重查只使用 GET。

## Higher-boundary coverage
- `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx` — Query／Preview／Apply／receipt/re-query state machine。
- `ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx` — 歷史請假唯讀查詢及舊審核回應契約。
- `tests/test_scheduling_staff_leave_review_boundary.py` — Scheduling route/application boundary。

- `tests/domains/scheduling/subsystems/scheduling/integration/test_leave_results_mysql.py` — 合意延期成功與衝突、原案人工代班日期與帳務、舊待辦續辦拒絕及同鍵讀回。
- `tests/domains/scheduling/subsystems/scheduling/integration/test_leave_results_contract.py` — 本人身分、typed transport 與退役卡片零副作用。

- `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover_mysql.py` — 工會服務中換人完整意願／邀請／入群／交接日流程、剩餘排班、實付保留、rollback、重送及混有歷史開工與延期需求時的換人待辦總數。
