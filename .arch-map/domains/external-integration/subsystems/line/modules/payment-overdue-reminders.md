# Module: payment-overdue-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
各期首次繳款私訊、自動補寄一次與逐次人工提醒，以及帳務警示內的排程設定。所有繳款提醒只寄目前有效的客戶私訊；Query 零寫入，Send 與 provider 前重讀同一期帳務及收件對象。補寄依原通知成功時間滿 24 小時、正式到期隔天及設定時段；任何已驗證本人私訊／按鈕回覆後停止自動補寄，未核銷款項保留原待辦並可人工提醒。不跨期合計、不無限重發、不新增財務狀態。
訂金、第一期、第二期清單／總數與寄送均須雙方簽約完成；Finance 唯讀查詢核對 Orders 目前契約識別及同案相符 `contract_completed` 事件，不符資格的舊待寄提醒取消，原金額與期限保持。

入帳通知僅讀原已提交核銷標記，帳務提示及待辦不自動寄送；專用人員命令建立客戶私訊，送前複核並阻擋舊自動來源。不新增帳務狀態。

## Implementation
- `subsystems/line/payment_receipt_notifications.py` — typed receipt todos, authenticated manual send and fresh provider guard.
- `infrastructure/mysql/payment_receipt_notification_repository.py` — marked settlement Query via Finance-owned deposit／second payment ports and existing delivery history.
- `api/routes/line_payment_receipt_notifications.py` — readonly receipt Query and explicit human Send.
- `ui_react/src/api/line_order_groups/payment_receipt_notification_client.ts`
- `ui_react/src/components/PaymentReceiptNoticeWorkbench.tsx`、`ui_react/src/components/PaymentReceiptNoticeWorkbench.css` — human-send prompt and durable todo presentation, composed in FinancePage.
- `subsystems/line/payment_reminder_schedule.py` — existing MESSAGE_SCHEDULES.payment_reminders definition／Taipei time calculations.
- `subsystems/line/payment_reminder_notifications.py` — initial/private follow-up worker and provider gate; existing UoW/queue only.
- `infrastructure/mysql/payment_reminder_notification_repository.py` — committed task success/history and verified private inbox replies; no Finance writes.
- `api/routes/line_payment_reminder_settings.py` — authenticated readonly Query／CAS Save composed in existing overdue router.
- `api/dependencies/line_worker_operation.py` — canonical additional worker wiring.
- `ui_react/src/api/line_order_groups/payment_reminder_schedule_client.ts`
- `ui_react/src/components/PaymentReminderSchedulePanel.tsx`、`ui_react/src/components/PaymentReminderSchedulePanel.css` — live schedule settings and public display-only sample.
- `ui_react/src/components/FinanceWarningWorkspace.tsx` — finance warning／schedule／reminder-content composition; scoped editor for initial reminders／first settled greeting／overdue and two receipt copies. Other notifications remain in LINE.
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
- `ui_react/src/components/FinanceReceiptsWorkspace.tsx`、`ui_react/src/pages/FinancePage.tsx` — 帳務收款「逾期提醒」主要入口，核對銀行入款保留案號。
- `ui_react/src/pages/LineManagementPage.tsx` — 原深連結導向 `#finance?tab=receipts&view=overdue`。

## Dependencies
- Finance: `client-finance/receipt-reconciliation` 的 typed `OverdueClientPayment`；LINE 不重算或改寫帳務。
- Delivery: 既有 committed task、audit、receipt／lease 與取消流程；來源快照放既有 correlation，沒有新 Preview fingerprint 或資料表。
- Identity: 所有期別沿既有唯一客戶綁定查詢。Reply source 為已驗證 `line_inbox_events`，僅讀本人 user message／postback existence，不帶出 raw payload。
- Finance: `ClientPaymentReminderFacts` 由 receipt-reconciliation owner 提供目前款項／契約與正式開始日期投影；LINE 不重算期款或日期。
- Configuration: existing versioned MESSAGE_SCHEDULES／MESSAGE_TEMPLATES; no new table or kind.

## Contracts
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §6.7～6.11。
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 款項期別、正式到期日及餘額。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_overdue_reminders_mysql.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_reminder_notifications_mysql.py` — opt-in isolated localhost schema clone, native locks/queue/receipt/private inbox and configuration CAS; synthetic provider only.
- ui_test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- layout_basis: 沿用 LINE 現有 module unit／React mirror 與 native MySQL cross-owner infrastructure 驗證邊界。

- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_receipt_notifications_mysql.py` — isolated native manual-only receipt queue, concurrency, reversal／binding guards and no automatic send.
