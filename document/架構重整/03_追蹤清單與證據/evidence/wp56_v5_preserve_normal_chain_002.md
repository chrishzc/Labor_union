# WP56 v5 Preserve Dataset Normal Chain 002

- Date: 2026-08-11
- Dataset: `lu_test_dataset_contract_signing_v5_preserve`
- Scenario: `WP56-V5-PRESERVE-002`
- Case: `WP56-E702D40C40B3`
- Execution mode: append-only new scenario; no existing case was overwritten.

## Result

`scripts/run_contract_signing_normal_chain.py` completed through typed applications.
The pre-execution snapshot had zero assignments and zero schedule days.
Finance correction replay matched its first receipt.

Both read-only verifiers returned `valid: true`:

- `scripts/verify_contract_signing_normal_chain.py`
- `scripts/verify_integrated_ui_validation_dataset.py`

Observed chain: four archived documents, two sent and two signed events, one
commitment and conversion event, settled deposit, one planned assignment, five
official service days, converted availability lock, and open staff payable of
NTD 12000.

Machine-readable receipt:
`validation/receipts/WP56-V5-PRESERVE-002-normal-chain.json`.
