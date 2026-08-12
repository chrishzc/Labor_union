# WP56 Client Atomic Failure 010

- Date: 2026-08-11
- Dataset: `lu_test_dataset_contract_signing_v5_preserve`
- Case: `WP56-240D05CE893F`

The case was stopped after the client contract had been sent and before client
signed return. A failure was injected into the Contract Completion collaborator
inside `ClientContractSigningApplication`'s MySQL transaction. After rollback,
the database had zero client signed events, zero contract-completed events, and
zero remaining obligations. The newly archived signed-return object was absent.

Machine-readable receipt:
`validation/receipts/WP56-CLIENT-ATOMIC-FAILURE-010_v5.json`.
