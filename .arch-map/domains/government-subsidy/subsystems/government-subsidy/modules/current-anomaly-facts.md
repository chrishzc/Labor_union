# Module: current-anomaly-facts

## Parent
- subsystem: `government-subsidy`

## Responsibility
`GOVSUB-001/002/004/007`已退出 runtime Anomalies。本 module只保留 Government Subsidy ledger／claim
roots的 deterministic validation與migration readback導覽；不再提供 current-fact predicate、Anomalies intent或bounded recheck。

## Consumers
- Government Subsidy owner validation／migration readback only；不再有 Anomalies runtime consumer。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/current-anomaly-facts/`
