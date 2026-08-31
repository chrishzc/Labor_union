subsystem: staff-payables
parent_domain: staff-payables
architecture: ../../../../../domains/staff-payables/subsystems/staff-payables/index.md
test_root: tests/domains/staff-payables/subsystems/staff-payables/
integration_root: tests/domains/staff-payables/subsystems/staff-payables/integration/
fixtures_root: tests/fixtures/
modules:
  historical-payment-settlement-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/historical_staff_payout_workbench.test.tsx
  payout-remediation-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/staff_payout_remediation_workbench.test.tsx
  overpayment-recovery-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/staff_overpayment_recovery_actions.test.tsx

# Routing notes
Current owner-local coverage includes payout reconciliation workflow/public contracts, payout repository recovery, payout-difference domain/workflow/schema-trigger contracts, overpayment recovery, accounts-payable export source/workflow contracts, the historical-baseline Staff Payables owner adapter, and the Staff Payables payout-remediation React workbench direct SUT. Other PAYOUT/anomaly projection tests belong to the Anomalies verification boundary and are not duplicated here.

# Deferred / higher-boundary
- `tests/test_accounts_payable_export_api_client.py` — imports legacy `ui.api_clients`; keep at the legacy UI boundary until Streamlit retirement/replacement reconciliation.
- Task97 and disposable-MySQL acceptance tests remain at their higher verification boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Staff Payables owner-local tests outside the documented Anomalies, legacy UI/API-client, Task97, disposable-MySQL/E2E, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
