# WP56 UI CI Invalid 001 v6

- Date: 2026-08-12
- UI: `http://127.0.0.1:8501`
- API: `http://127.0.0.1:8000`
- Dataset: `lu_test_dataset_contract_signing_v4`
- Scenario: `UI-CI-INVALID-001`
- Result: verified

Chrome loaded open review
`beclass-review:6e765a8abc3e109cccdfe2ddfd09032a466659d33fa1a3adf72ae3d3d9742a57`.
The review carried `phone_invalid` at version `0`. The repair retained its
existing client fields and changed only the invalid phone to `0912345678`.

The typed UI Preview returned fingerprint
`4b48bdc8001f5fc1fc747c4ccb034ae63d14f4626354e9be60d108445ca79eef`.
Chrome Apply returned owning record `DSV1-BECLASS-0002`, resulting version
`1`, review event `3`, and outbox `6`. Chrome then resubmitted the retained
Preview command without changing fields, reason, or command state; it returned
the same event and outbox identifiers.

Database re-observation confirmed exactly one resolution event, one resolution
outbox intent, and one command receipt for this review. Thus replay neither
created an additional owning record nor duplicated the resolution chain.

- Machine-readable receipt:
  `validation/receipts/UI-CI-INVALID-001-UI-037.json`
- Database oracle: captured in the machine-readable receipt.
