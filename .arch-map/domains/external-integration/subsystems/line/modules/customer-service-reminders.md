# Module: customer-service-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
React 六欄未結案客服清單及 Customer Service owner-backed bounded query projection；完成按鈕沿既有 update Preview／Apply，由原 owner 在單一 UoW 完成 ticket／escalation 並解除 hold，不建立 Push。來源由 canonical message events 與同事件 escalation 解讀，未知保留未知，多來源不重複計數。服務開始日群組按鈕建立的 `start-day-response:` 客服事件歸服務需求來源，供工會待辦查閱。

## Implementation
- primary: `ui_react/src/components/LineCustomerServiceReminderWorkbench.tsx`
- presentation: `ui_react/src/components/LineCustomerServiceReminderWorkbench.css`
- composition: `ui_react/src/pages/LineManagementPage.tsx` — 只替換 tickets 工作面。
- client: `ui_react/src/api/customer_service/customer_service_client.ts`
- schema: `ui_react/src/api/customer_service/customer_service_schemas.ts`
- entry: `api/routes/customer_service.py::GET /api/v1/customer-service/tickets/reminders`
- transport: `api/schemas/customer_service.py`
- application: `subsystems/customer_service/application.py`
- contract: `subsystems/customer_service/contracts.py`
- adapter: `infrastructure/mysql/customer_service_repository.py::list_reminders`
- 名稱唯讀 adapter: `infrastructure/line/messaging_api_adapter.py::display_names`；bounded Profile GET，缺值不冒充姓名。
- 完成 coordination: `subsystems/customer_service/escalation_application.py::complete_ticket_holds`、`infrastructure/mysql/customer_service_escalation_repository.py::active_for_ticket`；保留原 writer／CAS／audit。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6 React 客服案件提醒清單。
- depends_on: `complaint-ingress`, `feedback`, `customer-order-change-intake`, `line-identity-management` — 只讀既有 ticket events／escalation facts。
- dependency: existing Client name／Admin display name read projections；不寫 owner facts。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/customer-service-reminders/`
- UI integration coverage: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_customer_service_reminders.test.tsx`（沿用上層 LINE 整合測試歸屬）
- parent_regression: `ui_react/src/tests/line_management_page_real_data.test.tsx` — 既有跨頁 custom-current 呈現測試；本次過時的客服四個 cases 由 canonical reminder oracle 承接，其他 cases 保留。
- parent_regression: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_management_no_fake_mutation.test.tsx`

## Boundaries
Query 不 commit、不產生 receipt／outbox、不啟動 worker、不呼叫 provider；既有客服 Query／Preview／Apply 與手機 surface 保留。搜尋與 pagination 由 server 執行；只呈現最近10則原 owner 已保存的人員對話留言，不揭露已遮罩客訴、LINE user ID、電話或備註。完成操作只有原 application 的一次 outer commit，無 provider send。
