subsystem: anomalies
parent_domain: anomalies
architecture: ../../../../../domains/anomalies/subsystems/anomalies/index.md
test_root: tests/domains/anomalies/subsystems/anomalies/
integration_root: tests/domains/anomalies/subsystems/anomalies/integration/
fixtures_root: tests/fixtures/

# Routing notes
Focused Anomalies workflow, registry, projection, source and adapter contracts live here. Current owner-local coverage includes anomaly rulebook/action/recovery-context guards; finance/staff/client recovery anomaly consumers and projections; LINE-binding predicate guards; historical-order remediation outbox consumption; historical-baseline projection; and historical-baseline projector API/persistence readback contracts.

# Deferred / higher-boundary
- Cross-domain acceptance, Task97, release/migration/schema, disposable-MySQL and relocation-sensitive tests remain at their owning higher boundary.
- `tests/test_remote_anomaly_schedule_merge.py` remains higher because it spans Anomalies, Staff, HCM import, and legacy Scheduling UI state.
- `tests/test_historical_order_adoption_anomaly_consumer.py` remains higher because it also verifies a legacy UI finance-alert surface.
- Government-subsidy worker wiring remains at its cross-owner delivery boundary.
