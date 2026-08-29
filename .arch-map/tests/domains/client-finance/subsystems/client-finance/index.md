subsystem: client-finance
parent_domain: client-finance
architecture: ../../../../../domains/client-finance/subsystems/client-finance/index.md
test_root: tests/domains/client-finance/subsystems/client-finance/
integration_root: tests/domains/client-finance/subsystems/client-finance/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes cancellation direction, settlement query, over-refund recovery, payment transaction state, deposit lifecycle, receipt/refund overage, virtual-account resolution, precontract deposit obligation, order amount calculation, accounting source projection/query, and the historical-baseline Client Finance owner adapter. Anomaly reminder/projection tests that read Client Finance facts belong to the Anomalies verification boundary and are not duplicated here. Cross-domain contract-completion/cancellation/terms flows remain at their higher verification boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Client Finance owner-local tests outside the documented cross-domain, anomaly, migration/schema, disposable-MySQL/E2E, Task97, or legacy UI/API-client boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
