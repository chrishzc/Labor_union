# Module: leave-substitution

## Parent
- subsystem: `scheduling`

## Responsibility
協調正式排班案件在服務完成前的請假／代班 Query、Preview、Apply 與 committed-result readback；案件選單取 server-owned 進行中集合與有效正式排班日的交集，包含尚未開始服務的案件。完成後以 server-owned、case-bound 的 Scheduling→Payroll→Staff Payables typed lineage readback 顯示受影響服務人員的本案應付款與版本證據。

## Implementation
- `domains/scheduling/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `subsystems/scheduling/leave_substitution_linked_request_resolution.py` — 關聯待辦的 Preview 與 fresh-lock Apply 都驗證原服務日位於該請假期間；每批完成後查核所有案件的剩餘服務日，全部處理完才結案並建立通知工作。
- `subsystems/scheduling/substitution_payables_lineage.py`
- `subsystems/scheduling/service_handover_accounting.py` — 服務中換人的 owner-derived 前後薪資、實付、追償與客戶帳款比較。
- `api/routes/staff_leave_management.py`
- `api/routes/staff_leave_intake.py` — 月嫂請假 Preview／Apply 與本人待辦回讀。
- `line/static/staff_schedule.html` — 既有請假表單在結果未明時保留同一操作並提供查核入口。
- `api/routes/leave_substitution.py`
- `api/schemas/leave_substitution.py`
- `api/dependencies/leave_substitution.py`
- `infrastructure/mysql/leave_substitution_repository.py`
- `infrastructure/mysql/leave_substitution_impact_ports.py` — 使用同一份 Client Finance candidate 推導代班的月嫂付款期限與薪資影響。
- `infrastructure/mysql/staff_leave_intake_repository.py` — 請假待辦與受理後案件／客戶協調查詢；客戶 subject reference 以欄位正式 collation 比對字串化的客戶識別。
- `api/schemas/staff_leave_management.py` — Scheduling 請假待辦、pending／accepted_for_processing 完整總數分頁及處理 readback 的 typed transport views。
- `infrastructure/mysql/substitution_payables_lineage_repository.py`
- `ui_react/src/api/scheduling/leave_substitution_client.ts`
- `ui_react/src/api/scheduling/staff_leave_inbox_client.ts`
- `ui_react/src/api/scheduling/substitution_payables_lineage_client.ts`
- `ui_react/src/adapters/scheduling/leave_substitution_flow_adapter.ts`
- `ui_react/src/adapters/scheduling/leave_substitution_flow_store.ts` — 依已登入帳號與案件隔離尚未確認的 Apply；本機只保存原命令、預覽與操作識別，不保存登入憑證，重新開啟後沿原識別確認結果，觀察成功後清除。
- `ui_react/src/pages/SchedulingPage.tsx`
- `ui_react/src/pages/ServiceHandoverPage.tsx` — 原案件／指定服務段導向的換人專用頁，一次儲存並返回同案服務安排。
- `ui_react/src/adapters/scheduling/service_handover_navigation.ts`

## Dependencies
- outbound: `payroll` — Apply 由既有 outer Unit of Work 提交 payroll obligations；lineage 只讀其 immutable event/version。
- outbound: `staff-payables` — lineage 只讀 projection/evidence；換人經 typed owner application 同交易銜接合法 Payroll correction 的 projection／獨立追償，不擁有付款、匯出或 payout state。
- outbound: `external-integration/line` — 僅消費已關聯請假待辦與 notification intent readback。

## Verification routing
- default_boundary: Subsystem
- test_root: `ui_react/src/tests/service_handover_page.test.tsx`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover.py`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover_transaction.py`
- test_root: `ui_react/src/tests/substitution_payables_readback.test.tsx`
- test_root: `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx`
- test_root: `tests/test_leave_substitution_public_contract.py`
- integration_root: `tests/test_g13_leave_cancellation_disposable_mysql_e2e.py`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_customer_defer.py`
- integration_root: `ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx`
- layout_status: `custom_current`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/modules/leave-substitution.md`
