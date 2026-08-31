# Module: scheduling-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
`SCHEDULE-002/003/006`已退出 runtime Anomalies。本 leaf只保留 Scheduling owner validation／migration
readback導覽，不建立 current candidates、不查 Scheduling tables、不重算 owner rules、不執行修正。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/scheduling-current-issue/`

## Lifecycle
- `superseded_candidate`: 無 current runtime anomaly consumer；若 source／test retirement完成，移除本 leaf及其 inbound route。
