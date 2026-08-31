# Module: payroll-current-issue

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
`PAYOUT-002`已退出 runtime Anomalies。本 leaf只保留既有 Payroll owner validation／migration evidence
的導覽，不再投影 current issue、不計算delta、不寫Payroll或Staff Payables root。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/payroll-current-issue/`

## Lifecycle
- `superseded_candidate`: 無 current runtime anomaly consumer；若 source／test retirement完成，移除本 leaf及其 inbound route。
