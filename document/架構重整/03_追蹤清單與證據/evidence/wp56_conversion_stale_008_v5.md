# WP56 Commitment Conversion Stale 008

- Date: 2026-08-11
- Dataset: `lu_test_dataset_contract_signing_v5_preserve`
- Scenario: `WP56-V5-CONVERSION-STALE-008`
- Case: `WP56-A2578317CF4B`

After a shifted-date commitment mismatch had been rejected, the exact intent was
submitted with an intentionally stale expected order version. It returned
`stale_version`; DB inspection remained at zero assignments, zero schedule days,
and zero converted events. The exact retry then created one assignment, five
schedule days, and one conversion event.

Machine-readable receipt:
`validation/receipts/WP56-CONVERSION-STALE-008_v5.json`.
