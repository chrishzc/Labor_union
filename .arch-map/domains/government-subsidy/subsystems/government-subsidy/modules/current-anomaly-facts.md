# Module: current-anomaly-facts

## Parent
- subsystem: `government-subsidy`

## Responsibility
`GOVSUB-001/002/003/004/005/007` 已退出 runtime Anomalies。本 module 只保留 Government Subsidy ledger／claim roots 的 deterministic validation 與 migration readback 導覽；不再提供 current-fact predicate、Anomalies intent 或 bounded recheck。

## Consumers
- Government Subsidy owner validation／migration readback only；不再有 Anomalies runtime consumer。

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/integration/`
- GOVSUB-007 focused owner evidence: `test_government_subsidy_overpayment.py`、`test_government_subsidy_overpayment_workflow.py`。
- 不存在 dedicated `current-anomaly-facts` module test root；retired-code correctness 不回指 Anomalies consumer coverage。
