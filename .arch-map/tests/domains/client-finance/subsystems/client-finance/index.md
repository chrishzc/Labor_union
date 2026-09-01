subsystem: client-finance
parent_domain: client-finance
architecture: ../../../../../domains/client-finance/subsystems/client-finance/index.md
test_root: tests/domains/client-finance/subsystems/client-finance/
integration_root: tests/domains/client-finance/subsystems/client-finance/integration/
fixtures_root: tests/fixtures/
modules:
  obligation-planning:
    layout_status: custom_current
    test_root: tests/domains/client-finance/subsystems/client-finance/integration/test_client_finance_cancellation_direction.py
  historical-payment-settlement-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/historical_client_payment_workbench.test.tsx
  over-refund-recovery-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/client_over_refund_recovery_workbench.test.tsx
  settlement-remediation-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/client_settlement_remediation.test.tsx

# Routing notes
Current owner-local coverage includes cancellation direction, settlement query, over-refund recovery, payment transaction state, deposit lifecycle, receipt/refund overage, virtual-account resolution, precontract deposit obligation, order amount calculation, accounting source projection/query, the historical-baseline Client Finance owner adapter, and the Client Finance over-refund recovery React workbench direct SUT. Other anomaly reminder/projection tests that read Client Finance facts belong to the Anomalies verification boundary and are not duplicated here. Cross-domain contract-completion/cancellation/terms flows remain at their higher verification boundary.

# Flat-test audit
The current flat-test audit found no additional high-confidence Client Finance owner-local tests outside the documented cross-domain, anomaly, migration/schema, disposable-MySQL/E2E, Task97, or legacy UI/API-client boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
