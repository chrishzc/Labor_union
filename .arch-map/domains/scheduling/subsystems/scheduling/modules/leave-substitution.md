# Module: leave-substitution

## Parent
- subsystem: `scheduling`

## Responsibility
協調正式服務中的請假／代班 Query、Preview、Apply 與 committed-result readback；完成後只透過既有 Staff Payables typed GET 顯示受影響服務人員的本案應付款。

## Implementation
- `domains/scheduling/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `api/routes/staff_leave_management.py`
- `ui_react/src/api/scheduling/leave_substitution_client.ts`
- `ui_react/src/adapters/scheduling/leave_substitution_flow_adapter.ts`
- `ui_react/src/pages/SchedulingPage.tsx`

## Dependencies
- outbound: `payroll` — Apply 由既有 outer Unit of Work 提交 payroll obligations。
- outbound: `staff-payables` — 完成後使用既有 typed read-only query；不擁有付款、匯出或 payout state。
- outbound: `external-integration/line` — 僅消費已關聯請假待辦與 notification intent readback。

## Verification routing
- default_boundary: Subsystem
- test_root: `ui_react/src/tests/substitution_payables_readback.test.tsx`
- layout_status: `custom_current`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/modules/leave-substitution.md`
