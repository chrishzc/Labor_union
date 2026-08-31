# Module: anomaly-owner-remediation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
提供 Government Subsidy normal accounting／review／correction 的 deterministic validation與 owner readback；
`GOVSUB-003/005/007`均不形成 runtime Anomalies current issue，structural ambiguity與不完整owner facts fail closed。

## Implementation
- `subsystems/government_subsidy/ledger_workflow.py`
- `subsystems/government_subsidy/overpayment_workflow.py`

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/anomaly-owner-remediation/`

## Transaction boundary
- Government Subsidy normal owner Query／Preview／Apply維持單一outer UoW與fresh readback；不得新增GOVSUB-007 anomaly recovery或Anomalies recheck。
