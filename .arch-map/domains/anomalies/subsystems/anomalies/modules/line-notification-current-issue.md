# Module: line-notification-current-issue

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
只消費LINE-owned typed LINE-006 current-fact predicate，維持公開subject `case_no + notification_reason`；readback incomplete／unavailable時fail closed，不查LINE tables、不重算Delivery狀態、不寫LINE root。這是目前唯一 runtime anomaly consumer。

## Implementation
- primary:
  - `subsystems/anomalies/line_notification_current_issue_consumer.py`
  - `infrastructure/mysql/line_notification_current_issue_adapter.py`
  - `infrastructure/mysql/anomaly_runtime.py`

## Contracts
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — LINE-006 public identity與current-only reconcile。
- `subsystems/line/notification_failure_current_fact.py` — LINE owner typed readback。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/line-notification-current-issue/`

## Change triggers
Reconcile whenLINE-006 subject identity、typed readback consumer、fail-closed reconcile或runtime composition改變。
