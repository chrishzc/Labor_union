# Module: payment-overdue-reminders

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
各期繳款提醒、自動補寄一次與人工提醒，以及帳務排程。第一期首次提醒由開工問候 worker 併入同一則群組文字；其後逾期補寄及人工提醒均發客戶私聊。沿用原通知成功時間、正式到期、指定時段及同一期回覆停止條件。逾期卡含案號、期別、金額、期限及付款 Postback，Query 零寫入，Send 與 provider 前重讀帳務及收件對象。
訂金、第一期、第二期清單／總數與寄送均須雙方簽約完成；Finance 唯讀查詢核對 Orders 目前契約識別及同案相符 `contract_completed` 事件，不符資格的舊待寄提醒取消，原金額與期限保持。

入帳通知僅讀原已提交核銷標記，訂金、第一期、第二期三期入帳確認均已移除系統 Push 程式與後台範本編輯，改由工會人員在 LINE 官方帳號聊天後台使用預設訊息手動發送；同一 owner 衍生通知中心 `payment_receipt` 待辦與同案確認入口，人員點擊「已於官方帳號發送／標記已通知」後寫入 `line_command_receipts` 憑證與稽核並從待辦清單消除，任何殘留入帳推播工作在 provider 前取消，不新增帳務狀態。

取消結算通知讀取目前生效的 Orders 取消事件及其正式 Client Finance 結算、核銷餘額與專屬繳款資訊。人員預覽並確認後才建立既有 LINE 私訊工作，全額核銷才開放退款或補收完成通知。確認未投遞的取消工作可由新預覽接續，使用既有寄送工作與稽核。

## Implementation
- `subsystems/line/cancellation_notifications.py` — cancellation Preview、manual Send、provider freshness guard，沿用既有 LINE Unit of Work、寄送工作與稽核。
- `ui_react/src/api/line_order_groups/cancellation_notification_client.ts`、`ui_react/src/components/CancellationSettlementNotices.tsx` — 取消結果、案件帳務、客戶名冊共用預覽與狀態，範本深連結至 LINE 通知與發送。
- `subsystems/line/payment_receipt_notifications.py` — typed receipt todos, authenticated manual acknowledgment and retired push provider guard.
- `infrastructure/mysql/payment_receipt_notification_repository.py` — marked settlement Query via Finance-owned deposit／first／second payment ports and existing ack/delivery history.
- `api/routes/line_payment_receipt_notifications.py` — readonly receipt Query and explicit human Acknowledge (mark notified).
- `ui_react/src/api/line_order_groups/payment_receipt_notification_client.ts`
- `ui_react/src/components/PaymentReceiptNoticeWorkbench.tsx`、`ui_react/src/components/PaymentReceiptNoticeWorkbench.css` — manual-acknowledge prompt and durable todo presentation, composed in FinancePage.
- `subsystems/line/payment_reminder_schedule.py` — existing MESSAGE_SCHEDULES.payment_reminders definition／Taipei time calculations.
- `subsystems/line/payment_reminder_notifications.py` — initial/private follow-up worker and provider gate; existing UoW/queue only.
- `infrastructure/mysql/payment_reminder_notification_repository.py` — committed task success/history and verified private inbox replies; no Finance writes.
- `api/routes/line_payment_reminder_settings.py` — authenticated readonly Query／CAS Save composed in existing overdue router.
- `api/dependencies/line_worker_operation.py` — canonical additional worker wiring.
- `ui_react/src/api/line_order_groups/payment_reminder_schedule_client.ts`
- `ui_react/src/pages/PaymentReminderSettingsPage.tsx`、`ui_react/src/pages/PaymentReminderSettingsPage.css` — 帳務通知排程入口，舊範本深連結轉至 LINE。
- `ui_react/src/components/PaymentReminderSchedulePanel.tsx`、`ui_react/src/components/PaymentReminderSchedulePanel.css` — live schedule settings and public display-only sample.
- `ui_react/src/components/FinanceWarningWorkspace.tsx` — 逾期款項、待處理警示及排程；`view=overdue` 直接開啟逾期清單，舊 `view=reminder-content` 轉至 LINE 範本。
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
- `ui_react/src/components/FinanceReceiptsWorkspace.tsx`、`ui_react/src/pages/FinancePage.tsx` — 四區帳務的「逾期提醒」主入口；舊收款 overdue 深連結與核對銀行時的案號保留。
- `ui_react/src/pages/LineManagementPage.tsx` — 原深連結導向 `#finance?tab=receipts&view=overdue`。

- `ui_react/src/components/FinanceCaseNotice.tsx` — same-case period copy, recipient and existing history; last success time is separate from queued/failed state, no new cooldown; original-key recovery prevents duplicate requests.
- `infrastructure/mysql/client_payment_reminder_query_repository.py` — bounded per-case canonical period/balance/contract Query, including future dates and paid zero balances.

## Dependencies
- Finance: `client-finance/receipt-reconciliation` 的 typed `OverdueClientPayment`；LINE 不重算或改寫帳務。
- Delivery: 既有 committed task、audit、receipt／lease 與取消流程；來源快照放既有 correlation。取消通知 Preview fingerprint 涵蓋獨立更新的帳務、綁定、繳款資訊與文案，避免人工確認後寄出不同內容。
- Identity: 所有期別沿既有唯一客戶綁定查詢。Reply source 為已驗證 `line_inbox_events`，僅讀本人 user message／postback existence，不帶出 raw payload。
- Finance: `ClientPaymentReminderFacts` 由 receipt-reconciliation owner 提供目前款項／契約與正式開始日期投影；LINE 不重算期款或日期。
- Configuration: existing versioned MESSAGE_SCHEDULES／MESSAGE_TEMPLATES; no new table or kind.

## Contracts
- `.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §4.5 — GET `/api/v1/line/payment-overdue-reminders/cancellation-notices/{case_no}` 預覽，POST 同路徑加 `/send` 建立既有寄送工作。
- `.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md` §6.7～6.11。
- `.arch-map/requirements/04_Client_Finance_Domain.md` — 款項期別、正式到期日及餘額。

- `.arch-map/requirements/22_銀行流水匯入與帳務異常處理正式規格.md` §18.4 — GET `/api/v1/line/payment-overdue-reminders/cases/{case_no}` and POST `/cases/send`; manual case reminders may precede due date but retain current contract, unique recipient, positive balance, queue pending and fresh provider guards. All entries share existing delivery tasks and audit/history; requested/queued time never becomes sent time, original automatic schedule unchanged.

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_overdue_reminders_mysql.py`
- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_reminder_notifications_mysql.py` — opt-in isolated localhost schema clone, native locks/queue/receipt/private inbox and configuration CAS; synthetic provider only.
- ui_test_root: `ui_react/src/tests/domains/external-integration/subsystems/line/modules/payment-overdue-reminders/`
- layout_basis: 沿用 LINE 現有 module unit／React mirror 與 native MySQL cross-owner infrastructure 驗證邊界。

- integration_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_payment_receipt_notifications_mysql.py` — isolated native manual-only receipt queue, concurrency, reversal／binding guards and no automatic send. — 既有案例核對指定案件與期別精確命中；期別不符或案件不存在時回傳空結果，不替用其他案件或期別。
