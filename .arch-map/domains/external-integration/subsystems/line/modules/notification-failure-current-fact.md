# Module: notification-failure-current-fact

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以`case_no + notification_reason`組合既有Notification source／decision／manual-replay lineage與Delivery terminal result，提供LINE-006 typed zero-write current-fact readback。Notification保有applicability與lineage interpretation；Delivery保有task／attempt／terminal result；不新增aggregate persistence。
共用 LINE 處理投影判斷目前待辦、canonical target 與可用操作。結清在同一 LINE UoW 取消所選來源全部未送出工作並保存既有 audit／receipt 快照，保留失敗 attempt；processing／結果不明先核對。完整 owner readback 後同步移除 current projection，原來源不自動補送，新業務事件重新判斷。

## Implementation
- primary:
  - `domains/line/delivery.py` — Delivery 工作狀態轉換及保留的 attempt 結果；結清允許最終失敗轉取消。
  - `subsystems/line/notification_failure_current_fact.py`
  - `subsystems/line/notification_handling.py` — LINE 共用處理目標、待辦及操作資格。
  - `subsystems/line/ports.py` — existing LINE UoW ports gain only the typed readback／recheck members required by this Module.
  - `infrastructure/mysql/line_notification_repository.py`
  - `infrastructure/mysql/line_notification_anomaly_worker.py` — existing worker entry，改為bounded current recheck producer；不再逐decision寫legacy anomaly。
  - `subsystems/line/notification_manual_replay_application.py`
  - `api/routes/line_notification_rules.py` — `/failures/{issue_key}/skip/{preview|apply}`。
  - `api/schemas/line_notification_rules.py` — typed skip preview／apply／receipt。
  - `infrastructure/mysql/line_receipt_outbox_audit.py` — 既有 command receipt 的 locking read。
  - `subsystems/line/notification_rule_administration.py`
  - `subsystems/line/delivery_worker.py`
  - `infrastructure/mysql/line_unit_of_work.py`

- `api/routes/notification_tasks.py`、`api/routes/notification_task_actions.py` — 桌面／LIFF notification_failure 只讀 projection＋fresh owner，原 manual replay 資格及 writer。來源 IDs 為既有事件衍生定位；pending／processing／retryable 保留 predicate，不建立新 state。

## Contracts
- `document/架構重整/01_規格基線/17A_LINE_Gateway_Inbox與通知投遞正式規格.md` §4 — 共用判定、停送結清及 `LINE-CLOSE-01`～`07`。
- `manual-replay:{source_event_id}:{idempotency_key}` — 唯一replay lineage。
- `anomaly.recheck` — caller transaction內追加的既有bounded recheck intent。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/notification-failure-current-fact/`

## Change triggers
Reconcile whenLINE-006 applicability、replay lineage、fresh validation、Delivery terminal composition、recheck intent或canonical test root改變。
