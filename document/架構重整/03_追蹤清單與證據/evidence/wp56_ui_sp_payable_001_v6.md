# WP56 UI SP Payable 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- Scenario: `UI-SP-PAYABLE-001`
- Receipt: `validation/receipts/UI-SP-PAYABLE-001-UI-045.json`

Chrome selected the Accounts Payable query/export surface for `2026-08`. The
first and second controlled UI observations each displayed one payable totaling
NTD `7,200`. The archive/export button remained uninvoked.

This scenario is read-only: replay is a repeat typed query/re-observation with
unchanged facts, not an export, payment, settlement, or archive operation.
