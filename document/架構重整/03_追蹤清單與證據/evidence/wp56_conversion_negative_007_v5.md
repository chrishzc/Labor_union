# WP56 Commitment Conversion Negative 007

- Date: 2026-08-11
- Dataset: `lu_test_dataset_contract_signing_v5_preserve`
- Scenario: `WP56-V5-CONVERSION-NEGATIVE-007`
- Case: `WP56-58A6D2B66CFD`

The first Assignment Plan Apply used a five-day date set shifted by one day.
It preserved service-day conservation but differed from the effective commitment.
The application returned `commitment_execution_mismatch`; post-rejection DB
inspection found zero assignments, zero schedule days, and zero converted events.

The same active waiting lock was then reused for the exact intent. The recovery
Apply created one assignment, five schedule days, and one converted event.

Machine-readable receipt:
`validation/receipts/WP56-CONVERSION-NEGATIVE-007_v5.json`.
