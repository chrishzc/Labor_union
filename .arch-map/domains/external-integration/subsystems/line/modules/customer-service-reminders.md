# Module: customer-service-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
歷史客服工單保留於原資料表。歷史查閱、客服提醒、手機工作入口、工單回覆及人工升級新建退役。切換期間由既有 Customer Service writer 依版本和證據完成既有工單及解除暫停，無 LINE 發送。

## Implementation
- primary: `api/routes/customer_service.py`，舊工單摘要、列表、明細及提醒回 `410 Gone`，保留切換結案 Preview／Apply。
- `api/routes/line_order_change.py` 保留舊工單送件的 typed `410 Gone`，引導客戶於 LINE 官方帳號留言。
- management: `ui_react/src/pages/LineManagementPage.tsx` 將舊工單分頁連結導回身分與授權。
- application: `subsystems/customer_service/application.py`、`subsystems/customer_service/escalation_application.py`
- adapter: `infrastructure/mysql/customer_service_repository.py`

## Contracts
- `.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §2、§5.1。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/customer-service-reminders/`
- UI integration coverage: `ui_react/src/tests/domains/external-integration/subsystems/line/integration/line_customer_service_reminders.test.tsx` — 既有模擬案例確認舊工單連結轉到「身分與授權」；頁面不顯示歷史工單入口，也不發出客服查詢。

## Boundaries
退役的工單查閱 API 不讀取紀錄。工單 API 的切換結案持續履行版本驗證、原狀態與解除暫停證據檢核。
