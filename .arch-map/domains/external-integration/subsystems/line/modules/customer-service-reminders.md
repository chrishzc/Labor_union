# Module: customer-service-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
歷史客服工單留存供授權查閱。客服提醒、手機工作入口、工單回覆及人工升級新建退役。切換期間由既有 Customer Service writer 依版本和證據完成既有工單及解除暫停，無 LINE 發送。

## Implementation
- primary: `ui_react/src/components/LineCustomerServiceReminderWorkbench.tsx`，由 `ui_react/src/pages/LineManagementPage.tsx` 提供歷史紀錄入口。
- query: `ui_react/src/api/customer_service/customer_service_client.ts`
- entry: `api/routes/customer_service.py` 的授權工單明細、分頁與切換結案 Preview／Apply。
- application: `subsystems/customer_service/application.py`、`subsystems/customer_service/escalation_application.py`
- adapter: `infrastructure/mysql/customer_service_repository.py`

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §2、§5.1。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/customer-service-reminders/`
- UI integration coverage: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_customer_service_reminders.test.tsx`

## Boundaries
歷史查詢使用既有欄位及 server 分頁，無寫入或 provider effect。工單 API 的歷史結案持續履行版本驗證、原狀態與解除暫停證據檢核。
