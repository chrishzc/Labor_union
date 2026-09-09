# Module: current-anomaly-facts

## Parent
- subsystem: `scheduling`

## Responsibility
`SCHEDULE-002/003/006`已退出 runtime Anomalies。本 module只保留 Scheduling owner invariant validation、
closed unresolved evidence與migration readback；不寫Anomalies projection、不建立bounded anomaly recheck，也不取代Assignment Plan或Leave／Substitution owner workflow。

## Current owner evidence
- `infrastructure/mysql/historical_baseline_scheduling_owner_adapter.py` — 讀取 Scheduling-owned confirmed service date、effective generation、assignment official date與official service observations，供migration／historical readback使用。
- Scheduling transaction／validation modules仍是live owner invariants的authority；不存在Anomalies consumer。

## Verification
- `tests/domains/scheduling/subsystems/scheduling/integration/test_historical_baseline_scheduling_owner_adapter.py`
- 無獨立`current-anomaly-facts` test root；退役碼correctness留在既有Scheduling owner module／integration邊界。
