# Module: government-subsidy-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
只消費Government Subsidy owner typed current facts並投影／刪除canonical current issue；不查Government Subsidy tables、不重算金額、不寫owner roots。

## Implementation
- `subsystems/anomalies/government_subsidy_current_issue_consumer.py`
- `infrastructure/mysql/anomaly_runtime.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/government-subsidy-current-issue/`
