subsystem: government-subsidy
parent_domain: government-subsidy
architecture: ../../../../../domains/government-subsidy/subsystems/government-subsidy/index.md
test_root: tests/domains/government-subsidy/subsystems/government-subsidy/
integration_root: tests/domains/government-subsidy/subsystems/government-subsidy/integration/
fixtures_root: tests/fixtures/
modules:
  current-anomaly-facts:
    layout_status: canonical
    test_root: tests/domains/government-subsidy/subsystems/government-subsidy/modules/current-anomaly-facts/
  overpayment-recovery-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/government_overpayment_recovery_workbench.test.tsx
  reconciliation-register-query:
    layout_status: canonical
    test_root: tests/domains/government-subsidy/subsystems/government-subsidy/modules/reconciliation-register-query/

# Routing notes
Focused Government Subsidy owner domain/workflow/query/repository/API, owner-specific schema, payer-master, staff-payout funding and repository outbox-payload contracts live here. Anomaly projections sourced from subsidy roots stay under the Anomalies verification boundary; UI/legacy adapters, cross-boundary durable-job acceptance and disposable-MySQL tests remain at their higher owner boundary.

# GOVSUB-007 closure
The dedicated actual-over-lawful return reconciliation oracle is in the canonical integration root:
`tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_government_subsidy_overpayment.py` and
`test_government_subsidy_overpayment_workflow.py`. Disposable PyMySQL positive/negative Q/P/A/readback uses an ignored `lu_test_*` database.

# Flat-test audit
The current flat-test audit found no additional high-confidence Government Subsidy owner-local tests outside the documented Anomalies, UI/legacy adapter, durable-job, disposable-MySQL/E2E, release/migration, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
