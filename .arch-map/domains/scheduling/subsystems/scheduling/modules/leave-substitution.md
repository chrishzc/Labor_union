# Module: leave-substitution

## Parent
- subsystem: `scheduling`

## Responsibility
協調正式服務中的請假／代班 Query、Preview、Apply 與 committed-result readback；完成後以 server-owned、case-bound 的 Scheduling→Payroll→Staff Payables typed lineage readback 顯示受影響服務人員的本案應付款與版本證據。

## Implementation
- `domains/scheduling/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `subsystems/scheduling/substitution_payables_lineage.py`
- `api/routes/staff_leave_management.py`
- `api/routes/leave_substitution.py`
- `api/schemas/leave_substitution.py`
- `api/dependencies/leave_substitution.py`
- `infrastructure/mysql/substitution_payables_lineage_repository.py`
- `ui_react/src/api/scheduling/leave_substitution_client.ts`
- `ui_react/src/api/scheduling/substitution_payables_lineage_client.ts`
- `ui_react/src/adapters/scheduling/leave_substitution_flow_adapter.ts`
- `ui_react/src/pages/SchedulingPage.tsx`

## Dependencies
- outbound: `payroll` — Apply 由既有 outer Unit of Work 提交 payroll obligations；lineage 只讀其 immutable event/version。
- outbound: `staff-payables` — lineage 只讀其 projection/evidence，不擁有付款、匯出或 payout state。
- outbound: `external-integration/line` — 僅消費已關聯請假待辦與 notification intent readback。

## Verification routing
- default_boundary: Subsystem
- test_root: `ui_react/src/tests/substitution_payables_readback.test.tsx`
- layout_status: `custom_current`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/modules/leave-substitution.md`
