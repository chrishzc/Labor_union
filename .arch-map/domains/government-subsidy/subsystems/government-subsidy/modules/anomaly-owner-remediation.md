# Module: anomaly-owner-remediation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
提供GOVSUB-003 deterministic rebuild、GOVSUB-005 versioned exact Scheduling lineage，以及GOVSUB-007
return-with-excess原子核銷／recovery readback／reconciliation；structural ambiguity與不完整owner facts fail closed。

## Implementation
- `domains/government_subsidy/anomaly_remediation.py`
- `subsystems/government_subsidy/anomaly_owner_readback.py`
- `subsystems/government_subsidy/anomaly_recovery_workflow.py`
- `infrastructure/mysql/government_subsidy_anomaly_owner_repository.py`

## Verification
- test_root: `tests/domains/government-subsidy/subsystems/government-subsidy/modules/anomaly-owner-remediation/`

## Transaction boundary
- GOVSUB-007 `actual > lawful remaining`只可由專用Preview／Confirm／Apply在單一Government Subsidy outer UoW同時核銷lawful return、建立excess recovery、append receipt/outbox/recheck並commit；normal／partial reconciliation維持既有workflow。
