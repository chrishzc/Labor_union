# Module: leave-substitution

## Parent
- subsystem: `scheduling`

## Responsibility
雙方合意延期以月嫂提議、客戶群組確認成立。正式確認的檔期衝突依 Scheduling 契約交由管理員在原案件直接調整排班；人工局部代班與服務中換人沿各自 writer 銜接 Scheduling、Payroll、Staff Payables 回讀。

## Implementation
- `domains/scheduling/leave_substitution.py`
- `subsystems/scheduling/leave_substitution_workflow.py`
- `subsystems/scheduling/leave_substitution_linked_request_resolution.py` — `source_observed`：保留舊關聯模型及其歷史契約。正式 workflow 在舊收據讀回後拒絕新的關聯操作。
- `subsystems/scheduling/substitution_payables_lineage.py`
- `subsystems/scheduling/service_handover_accounting.py` — 服務中換人的 owner-derived 前後薪資、實付、追償與客戶帳款比較。
- `api/routes/staff_leave_management.py`
- `api/routes/staff_leave_intake.py` — 本人 leave-results Query／Preview（檔期衝突與天數守恆預檢）／Propose（群組零推播提案）；舊直送及請假申請退役，歷史 readback 保留。
- `line/static/staff_schedule.html` — 月嫂個人班表。合意延期 LIFF 使用共用月曆、配對預檢及群組提案。
- `domains/scheduling/leave_result.py` — 明確原日／新日與順延／代班 typed intent。
- `infrastructure/mysql/leave_result_repository.py` — 現有 Scheduling result store 的 leave-v1 envelope、本人日期與版本驗證。
- `subsystems/scheduling/service_start_workflow.py` — 合意延期與服務中換人共用既有交易機制。延期正式確認衝突回滾新需求與正式寫入。
- `infrastructure/mysql/service_start_arrangement.py` — 請假委派 canonical Leave/Substitution writer。
- `ui_react/src/components/ServiceStartSubstituteWorkbench.tsx` — 呈現服務中換人協調及正式排班結果。
- `line/static/mobile_admin.html` — 只列合資格的服務中換人需求。
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
- `ui_react/src/pages/SchedulingPage.tsx` — 排班月曆與國定假日政策。舊請假連結經唯讀核對案件與權限後導向原案排班。
- `ui_react/src/pages/ServiceHandoverPage.tsx` — 原案件／指定原服務段帶入剩餘日期，重用代班意願、邀請與加入，工會填交接日一次保存正式 handover 與帳務。
- `ui_react/src/adapters/scheduling/service_handover_navigation.ts`

- `infrastructure/mysql/service_handover_repository.py` — 原區段換人 Query／初次意願命令，沿共用 result store 的 handover-v1 envelope，不新增表或狀態。

## Dependencies
- outbound: `orders/orders/module:official-service-date-correction` — 人工局部代班沿正式多月嫂排班，同交易提交班表與帳務。
- outbound: `scheduling/staff-monthly-calendar` — 合意延期 LIFF 重用月份格線與檔期標示，以本人月班表查詢供選日參考。
- outbound: `payroll` — Apply 由既有 outer Unit of Work 提交 payroll obligations；lineage 只讀其 immutable event/version。
- outbound: `staff-payables` — lineage 只讀 projection/evidence；換人經 typed owner application 同交易銜接合法 Payroll correction 的 projection／獨立追償，不擁有付款、匯出或 payout state。
- outbound: `external-integration/line` — 服務中換人的意願、單人原案件群組邀請、加入證據與無按鈕正式日期表，僅建立 committed delivery。

## Contracts
- `architecture_declared`：`document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` §3.3、§3.4.1 擁有衝突處理及人工局部代班契約，不使用代班待辦識別、版本或結案。
- `architecture_declared`：`document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md` 擁有代班待辦分頁、歷史請假工作面及續辦入口的退役邊界；歷史記錄與成功收據保留讀取。

## Verification routing
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/leave-substitution/`
- default_boundary: Subsystem
- test_root: `ui_react/src/tests/service_handover_page.test.tsx`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover.py`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover_transaction.py`
- test_root: `ui_react/src/tests/substitution_payables_readback.test.tsx`
- test_root: `ui_react/src/tests/scheduling_leave_substitution_flow.test.tsx`
- test_root: `ui_react/src/tests/leave_substitution_client.test.ts`
- test_root: `tests/test_leave_substitution_public_contract.py`
- integration_root: `tests/test_g13_leave_cancellation_disposable_mysql_e2e.py`
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_staff_leave_customer_defer.py`
- integration_root: `ui_react/src/tests/scheduling_staff_leave_inbox_flow.test.tsx`
- layout_status: `custom_current`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/modules/leave-substitution.md`

- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_leave_results_mysql.py`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/service-start/service_start_workbench.test.tsx`

- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_service_handover_mysql.py`
