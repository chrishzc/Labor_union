subsystem: client-finance
parent_domain: client-finance
architecture: ../../../../../domains/client-finance/subsystems/client-finance/index.md
test_root: tests/domains/client-finance/subsystems/client-finance/
integration_root: tests/domains/client-finance/subsystems/client-finance/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes cancellation direction, settlement query and over-refund recovery. Anomaly reminder/projection tests that read Client Finance facts belong to the Anomalies verification boundary and are not duplicated here.
