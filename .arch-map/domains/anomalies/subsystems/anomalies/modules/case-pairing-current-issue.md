# Module: case-pairing-current-issue

## Parent
- subsystem: `anomalies`

## Responsibility
`BECLASS-001`是 Case Import／Client owner follow-up，`IMPORT-003`已退出 runtime Anomalies。本 leaf
不再消費 Case Import pairing predicate或建立 current issue；owner facts回 Case Import正常 intake／follow-up。

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/case-pairing-current-issue/`

## Lifecycle
- `superseded_candidate`: 無 current runtime anomaly consumer；若 source／test retirement完成，移除本 leaf及其 inbound route。
