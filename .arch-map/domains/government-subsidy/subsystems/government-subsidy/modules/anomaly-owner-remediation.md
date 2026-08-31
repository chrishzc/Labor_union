# Module: anomaly-owner-remediation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
提供GOVSUB-003 deterministic rebuild、GOVSUB-005 versioned exact Scheduling lineage，以及GOVSUB-007 recovery readback／reconciliation；structural ambiguity與不完整owner facts fail closed。

## Implementation
- `domains/government_subsidy/anomaly_remediation.py`
- `subsystems/government_subsidy/anomaly_owner_readback.py`
- `subsystems/government_subsidy/anomaly_recovery_workflow.py`
- `infrastructure/mysql/government_subsidy_anomaly_owner_repository.py`

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/anomaly-owner-remediation/`

## Known boundary
- GOVSUB-007 lawful payout＋excess recovery atomic creation remains `BOUNDARY_REQUIRED_GOVSUB007_ATOMIC_EXCESS_UOW`.
