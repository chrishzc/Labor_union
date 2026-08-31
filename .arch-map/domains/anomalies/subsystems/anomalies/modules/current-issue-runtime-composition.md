# Module: current-issue-runtime-composition

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
在既有durable recheck runtime組合owner-specific typed snapshot reader與Anomalies consumer；不新增owner
mutation、business predicate或public entry。

## Implementation
- `infrastructure/mysql/anomaly_runtime.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/current-issue-runtime-composition/`
