# Module: payment-overdue-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
工會各期繳款逾期待辦與逐次人工提醒。訂金只寄客戶私訊，第一、二期只寄原案件群組；Query 零寫入，Send 與 provider 前重讀同一筆期別帳務及收件對象。沒有自動逾期催繳、跨期合計、私訊替代群組或新財務狀態。
訂金、第一期、第二期清單／總數與寄送均須雙方簽約完成；Finance 唯讀查詢核對 Orders 目前契約識別及同案相符 `contract_completed` 事件，不符資格的舊待寄提醒取消，原金額與期限保持。

## Implementation
- `subsystems/line/payment_overdue_reminders.py`
- `infrastructure/mysql/payment_overdue_reminder_repository.py`
- `api/dependencies/payment_overdue_reminders.py`
- `api/routes/line_payment_overdue_reminders.py`
- `api/main.py`
- `infrastructure/mysql/line_unit_of_work.py`
- `subsystems/line/ports.py`
- `subsystems/line/delivery_worker.py`
- `ui_react/src/api/line_order_groups/payment_overdue_reminder_client.ts`
- `ui_react/src/components/PaymentOverdueReminderWorkbench.tsx`
- `ui_react/src/components/PaymentOverdueReminderWorkbench.css`
- `ui_react/src/pages/LineManagementPage.tsx` — 日常作業「繳款逾期」入口。

## Dependencies
- Finance: `client-finance/receipt-reconciliation` 的 typed `OverdueClientPayment`；LINE 不重算或改寫帳務。
- Delivery: 既有 committed task、audit、receipt／lease 與取消流程；來源快照放既有 correlation，沒有新 Preview fingerprint 或資料表。
- Identity: 訂金沿既有唯一客戶綁定查詢；群組沿既有案件群組版本。

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6.10。
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 款項期別、正式到期日及餘額。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_overdue_reminders_mysql.py`
- ui_test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- layout_basis: 沿用 LINE 現有 module unit／React mirror 與 native MySQL cross-owner infrastructure 驗證邊界。
