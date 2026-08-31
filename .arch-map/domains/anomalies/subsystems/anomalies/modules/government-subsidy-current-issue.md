# Module: government-subsidy-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
`GOVSUB-001/002/004/007`已退出 runtime Anomalies。本 leaf只保留 Government Subsidy owner
validation／migration readback導覽，不投影／刪除 current issue、不查Government Subsidy tables、不重算金額、不寫owner roots。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/government-subsidy-current-issue/`

## Lifecycle
- `superseded_candidate`: 無 current runtime anomaly consumer；若 source／test retirement完成，移除本 leaf及其 inbound route。
