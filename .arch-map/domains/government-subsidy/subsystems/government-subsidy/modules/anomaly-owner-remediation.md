# Module: anomaly-owner-remediation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
提供 Government Subsidy normal accounting／review／correction 的 deterministic validation與 owner readback；
`GOVSUB-003/005/007`均不形成 runtime Anomalies current issue，structural ambiguity與不完整owner facts fail closed。

## Implementation
- `domains/government_subsidy/overpayment.py`
- `subsystems/government_subsidy/ledger_workflow.py`
- `subsystems/government_subsidy/overpayment_query.py`
- `subsystems/government_subsidy/overpayment_workflow.py`
- `infrastructure/mysql/government_subsidy_repository.py`
- `api/routes/government_subsidy.py` (owner-only excess reconciliation transport)
- `api/schemas/government_subsidy.py`

## Verification
- higher_boundary: tests/domains/government-subsidy/subsystems/government-subsidy/integration/
- focused: `test_government_subsidy_overpayment.py`, `test_government_subsidy_overpayment_workflow.py`

## Transaction boundary
- Government Subsidy normal owner Query／Preview／Apply維持單一outer UoW與fresh readback；GOVSUB-007 actual-over-lawful uses a dedicated typed owner operation and immutable recovery root, never an Anomalies issue or Anomalies recheck。
