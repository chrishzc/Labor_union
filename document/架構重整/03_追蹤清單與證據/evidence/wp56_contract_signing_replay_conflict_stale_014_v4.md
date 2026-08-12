# WP56 Contract Signing Replay Conflict Stale 014 v4

- Date: 2026-08-11
- Database: `lu_test_dataset_contract_signing_v4`
- Case: `WP56-CE63803E5B48`

The running validation API replayed the existing staff and client signed
documents with their original idempotency keys and current sent document
versions. Both returned the original receipt. The same keys with changed bytes
returned typed `409 contract_signature_idempotency_conflict`.

New keys with stale document version `1` returned typed `409
contract_document_version_stale` for both sides. Before and after counts stayed
at four contract document versions and four signing events.

Receipt: `validation/receipts/WP56-CONTRACT-SIGNING-REPLAY-CONFLICT-STALE-014_v4.json`.
Focused regression: 13 passed across contract-signing API, UI client, staff and
client application tests.
