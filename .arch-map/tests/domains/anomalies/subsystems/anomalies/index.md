subsystem: anomalies
parent_domain: anomalies
architecture: ../../../../../domains/anomalies/subsystems/anomalies/index.md
test_root: tests/domains/anomalies/subsystems/anomalies/
integration_root: tests/domains/anomalies/subsystems/anomalies/integration/
fixtures_root: tests/fixtures/

# Routing notes
Focused Anomalies workflow, registry, current-only projection, source and adapter contracts live here. Current owner-local coverage includes closed issue identity／typed 410／fresh recheck guards; anomaly rulebook/action/recovery-context guards; finance/staff/client recovery consumers; LINE-binding predicate guards; `test_line_identity_current_issue_consumer.py`對typed LINE readback、合法雙角色抑制、role-scoped conflict與redacted details的cross-subsystem oracle；以及其他owner projection contracts。

Access security-alert composition is cross-subsystem: Access owner-local delivery/retry tests remain under the Access root, while `system_alerts` projection/service and schema oracles remain at the Anomalies/schema higher boundary.

# Deferred / higher-boundary
- Cross-domain acceptance, Task97, release/migration/schema and disposable-MySQL tests remain at their owning higher boundary.
- `tests/test_anomaly_reclassification_schema_contract.py` remains at the schema verification boundary.
- `tests/test_anomaly_bootstrap_import.py` remains at the application-composition/OpenAPI boundary.
- `tests/test_remote_anomaly_schedule_merge.py` remains higher because it spans Anomalies, Staff, HCM import, and legacy Scheduling UI state.
- `tests/test_historical_order_adoption_anomaly_consumer.py` remains higher because it also verifies a legacy UI finance-alert surface.
- Government-subsidy worker wiring remains at its cross-owner delivery boundary.
- `tests/test_system_alert_service.py` — Anomalies-owned projection/query/claim/resolve contract at the flat higher boundary.
- `tests/test_system_alert_current_projection_schema.py` — schema/static projection contract; do not move into Access.

# Flat-test audit
The current flat-test audit found no additional high-confidence Anomalies owner-local tests outside the documented cross-domain, application-composition, Task97, release/migration/schema, disposable-MySQL/E2E, legacy UI, or cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
