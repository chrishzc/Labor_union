# Module: order-pre-start-notification-source

## Parent
- subsystem: `external-integration/line`

## Responsibility
[RETIRED SOURCE] 2026-11-12 起，開工當天群組服務狀況詢問、正常結案問卷群組邀請與第二期款群組通知不再投影來源事件，也不再 Push 到任何群組；原 scanner／projector／worker 與兩個來源 repository 已移除，`order_pre_start_notification_sources` worker 不再註冊。

仍保留的最小責任：
- 舊群組訊息上的 `start-day:` 按鈕仍可被驗證並以 `line_webhook_reply` Reply-only 確認；選「需要協助」時照舊建立 Customer Service 服務進度待辦。不補 Push。
- provider 前守門：殘留的 `order_service_start_day`／`order_service_start_day_response`（非 Reply ack）、`order_service_completion`、`client_second_payment_reminder`／`client_second_payment_settled` 工作一律取消。
- 第二期款改走私訊：到期當天由 `payment-overdue-reminders` 的繳款提醒 worker 發客戶私訊；核銷成功通知由人員於財務待辦確認後寄客戶私訊。
- `notification_rules` 拒絕儲存 `order.service_start_day`、`order.service_completed` 及 `order.pre_start_reminder`／`order.second_payment_reminder`；第二期款兩個事件不封鎖；`config/notification_rules.json` 預設不含群組規則。

## Implementation
- `subsystems/line/service_start_day.py` — 舊按鈕 postback 與開工 Push 守門。
- `infrastructure/mysql/service_start_day_repository.py` — 舊按鈕回覆 context 與 Reply ack 現行性。
- `subsystems/line/service_completion_notifications.py` — 殘留結案問卷工作守門（取消）。
- `subsystems/line/second_payment_notifications.py` — 殘留第二期款群組工作守門（取消）。
- `subsystems/line/notification_source_adapters.py` — 僅保留 Orders／Finance／Scheduling committed outbox adapter。
- `domains/line/notification_rules.py` — 開工詢問與結案問卷事件儲存拒絕。

## Dependencies
- inbound: `api/dependencies/line_worker_operation.py` 路由已驗證 `start-day:` group postback。
- outbound: Customer Service `create_or_append`（協助待辦）、既有 delivery task cancel。

## Contracts
- `document/架構重整/01_規格基線/17A_LINE_Gateway_Inbox與通知投遞正式規格.md`
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`

## Verification routing
layout_status: `custom_current`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_source_adapters.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_order_reminder_worker_wiring.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_policy.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_service_start_day_postback.py`
