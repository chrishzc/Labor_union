# Module: notification-failure-current-fact

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以`case_no + notification_reason`組合既有Notification source／decision／manual-replay lineage與Delivery terminal result，提供LINE-006 typed zero-write current-fact readback。Notification保有applicability與lineage interpretation；Delivery保有task／attempt／terminal result；不新增aggregate persistence。

## Implementation
- primary:
  - `subsystems/line/notification_failure_current_fact.py`
  - `subsystems/line/ports.py` — existing LINE UoW ports gain only the typed readback／recheck members required by this Module.
  - `infrastructure/mysql/line_notification_repository.py`
  - `infrastructure/mysql/line_notification_anomaly_worker.py` — existing worker entry，改為bounded current recheck producer；不再逐decision寫legacy anomaly。
  - `subsystems/line/notification_manual_replay_application.py`
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
