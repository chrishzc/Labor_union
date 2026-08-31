# Module: current-anomaly-facts

## Parent
- subsystem: `scheduling`

## Responsibility
提供 `SCHEDULE-002`、`SCHEDULE-003`、`SCHEDULE-006` 的 typed、zero-write current-fact readback、closed unresolved reasons與Scheduling-owned bounded recheck request；不寫Anomalies projection，不取代Assignment Plan或Leave／Substitution owner workflow。外層MySQL composition才把request轉成既有Anomalies intent。

## Implementation
- `subsystems/scheduling/current_anomaly_facts.py`
- `infrastructure/mysql/scheduling_current_issue_adapter.py`
- `infrastructure/mysql/scheduling_anomaly_recheck_sink.py`

## Consumers
- `subsystems/anomalies/scheduling_current_issue_consumer.py`
- MySQL outward adapter（只組合 Scheduling-owned facts）

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/current-anomaly-facts/`
