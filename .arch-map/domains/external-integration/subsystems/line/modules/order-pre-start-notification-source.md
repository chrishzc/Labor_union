# Module: order-pre-start-notification-source

## Parent
- subsystem: `external-integration/line`

## Responsibility
- `service_start_day_greeting` worker 依正式開工日與帳務排程向本案群組發一則文字，第一期款有餘額才併入同一則。正式排班、群組綁定與餘額於投遞前重驗，舊開工卡片來源不得投遞。
- 開工當天群組付款文字指令驗證本案客戶身分後使用 `line_webhook_reply`。舊服務回報按鈕與未送出的回覆不再處理業務或投遞。
- 完工問卷與第二期款群組來源只保留投遞前取消守門。通用通知規則不得另發同一開工問候。

## Implementation
- `subsystems/line/service_start_day.py` — 開工群組問候排程、付款文字指令與投遞守門。
- `infrastructure/mysql/service_start_day_repository.py` — 正式開工候選、群組與身分 context、投遞現行性。
- `subsystems/line/service_completion_notifications.py` — 殘留結案問卷工作守門（取消）。
- `subsystems/line/second_payment_notifications.py` — 殘留第二期款群組工作守門（取消）。
- `subsystems/line/notification_source_adapters.py` — 僅保留 Orders／Finance／Scheduling committed outbox adapter。
- `domains/line/notification_rules.py` — 開工詢問與結案問卷事件儲存拒絕。

## Dependencies
- inbound: `api/dependencies/line_worker_operation.py` 組裝開工問候 worker 與群組 Reply 路由。
- outbound: Scheduling 正式開工、Client Finance 第一期款、既有付款回報與 delivery task。

## Contracts
- `.arch-map/requirements/17A_LINE_Gateway_Inbox與通知投遞正式規格.md`
- `.arch-map/requirements/20_LINE客服與月嫂自助服務正式規格.md`

## Verification routing
layout_status: `custom_current`

- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_line_notification_source_adapters.py`
- test_root: `tests/domains/external-integration/subsystems/line/infrastructure/test_line_order_reminder_worker_wiring.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_order_pre_start_notification_policy.py`
- test_root: `tests/domains/external-integration/subsystems/line/subsystems/test_service_start_day_postback.py`
