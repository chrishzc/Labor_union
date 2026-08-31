# Module: current-anomaly-facts

## Parent
- subsystem: `scheduling`

## Responsibility
`SCHEDULE-002/003/006`已退出 runtime Anomalies。本 module只保留 Scheduling owner invariant validation、
closed unresolved evidence與migration readback；不寫Anomalies projection、不建立bounded anomaly recheck，也不取代Assignment Plan或Leave／Substitution owner workflow。

## Consumers
- `subsystems/anomalies/scheduling_current_issue_consumer.py`
- MySQL outward adapter（只組合 Scheduling-owned facts）

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/current-anomaly-facts/`
