# WP56 Occupancy Conflict Pair v5

- Date: 2026-08-11
- Dataset: `lu_test_dataset_contract_signing_v5_preserve`
- Shared service window: 2035-05-01 through 2035-05-05

Two independent cases completed commitment and deposit reconciliation before either
was converted. `WP56-B99F914AF205` was then converted successfully. When
`WP56-73DD276298F0` attempted availability-lock acquisition for the same staff
and window, the database returned 17 assignment/schedule conflicts and created
no assignment, schedule day, or converted event for the rejected case.

The runner invokes the subsystem directly and therefore sees its internal
conflict payload. The public waiting-deposit-lock API maps this payload to typed
`409 conflict` code `waiting_lock_conflict`; this mapping is covered by the
focused API regression test.

Machine-readable receipt:
`validation/receipts/WP56-OCCUPANCY-CONFLICT-PAIR_v5.json`.
