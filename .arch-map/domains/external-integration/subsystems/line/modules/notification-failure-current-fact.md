# Module: notification-failure-current-fact

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以`case_no + notification_reason`組合既有Notification source／decision／manual-replay lineage與Delivery terminal result，提供LINE-006 typed zero-write current-fact readback。Notification保有applicability與lineage interpretation；Delivery保有task／attempt／terminal result；不新增aggregate persistence。
2026-10-01 人工裁決：同一 owner snapshot 的 warning skip 保存既有 LINE audit／receipt；只移除人工提醒，失敗數與投遞結果保留。source／result 改變後可再次提醒；完整 owner readback 後同步移除 current projection 並追加 bounded recheck，無 provider 效果。

## Implementation
- primary:
  - `subsystems/line/notification_failure_current_fact.py`
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

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — LINE-006 owner readback、manual replay與terminal predicate。
- `manual-replay:{source_event_id}:{idempotency_key}` — 唯一replay lineage。
- `anomaly.recheck` — caller transaction內追加的既有bounded recheck intent。

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/notification-failure-current-fact/`

## Change triggers
Reconcile whenLINE-006 applicability、replay lineage、fresh validation、Delivery terminal composition、recheck intent或canonical test root改變。
