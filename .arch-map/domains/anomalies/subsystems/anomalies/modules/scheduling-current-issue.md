# Module: scheduling-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
只消費 Scheduling typed current-fact readbacks，建立 `SCHEDULE-002/003/006` current candidates；不查 Scheduling tables、不重算 owner rules、不執行修正。

## Implementation
- `subsystems/anomalies/scheduling_current_issue_consumer.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/scheduling-current-issue/`
