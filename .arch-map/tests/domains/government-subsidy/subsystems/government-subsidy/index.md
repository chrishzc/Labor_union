subsystem: government-subsidy
parent_domain: government-subsidy
architecture: ../../../../../domains/government-subsidy/subsystems/government-subsidy/index.md
test_root: tests/domains/government-subsidy/subsystems/government-subsidy/
integration_root: tests/domains/government-subsidy/subsystems/government-subsidy/integration/
fixtures_root: tests/fixtures/

# Routing notes
Focused Government Subsidy owner domain/workflow/query/repository/API, owner-specific schema, payer-master, staff-payout funding and repository outbox-payload contracts live here. Anomaly projections sourced from subsidy roots stay under the Anomalies verification boundary; UI/legacy adapters, cross-boundary durable-job acceptance and disposable-MySQL tests remain at their higher owner boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Government Subsidy owner-local tests outside the documented Anomalies, UI/legacy adapter, durable-job, disposable-MySQL/E2E, release/migration, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
