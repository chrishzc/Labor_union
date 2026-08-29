subsystem: staff-payables
parent_domain: staff-payables
architecture: ../../../../../domains/staff-payables/subsystems/staff-payables/index.md
test_root: tests/domains/staff-payables/subsystems/staff-payables/
integration_root: tests/domains/staff-payables/subsystems/staff-payables/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes payout reconciliation workflow/public contracts, payout repository recovery, payout-difference domain/workflow/schema-trigger contracts, overpayment recovery, accounts-payable export source/workflow contracts, and the historical-baseline Staff Payables owner adapter. PAYOUT/anomaly projection tests belong to the Anomalies verification boundary and are not duplicated here.

# Deferred / higher-boundary
- `tests/test_accounts_payable_export_api_client.py` — imports legacy `ui.api_clients`; keep at the legacy UI boundary until Streamlit retirement/replacement reconciliation.
- Task97 and disposable-MySQL acceptance tests remain at their higher verification boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Staff Payables owner-local tests outside the documented Anomalies, legacy UI/API-client, Task97, disposable-MySQL/E2E, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
