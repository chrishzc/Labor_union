# Module: case-pairing-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
只消費Case Import typed pairing predicate；不查Case Import tables、不選候選、不修改mapping。

## Implementation
- `subsystems/anomalies/case_pairing_current_issue_consumer.py`
- `infrastructure/mysql/anomaly_runtime.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/case-pairing-current-issue/`
