subsystem: staff-payables
parent_domain: staff-payables
architecture: ../../../../../domains/staff-payables/subsystems/staff-payables/index.md
test_root: tests/domains/staff-payables/subsystems/staff-payables/
integration_root: tests/domains/staff-payables/subsystems/staff-payables/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes payout repository recovery, overpayment recovery, and accounts-payable export source/workflow contracts. PAYOUT/anomaly projection tests belong to the Anomalies verification boundary and are not duplicated here.

# Deferred / higher-boundary
- `tests/test_accounts_payable_export_api_client.py` — imports legacy `ui.api_clients`; keep at the legacy UI boundary until Streamlit retirement/replacement reconciliation.
