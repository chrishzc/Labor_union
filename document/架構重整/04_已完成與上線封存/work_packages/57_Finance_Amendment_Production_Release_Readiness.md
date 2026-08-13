---
doc_type: validation-closeout
declared_status: completed
date: 2026-08-11
owner: finance-architecture
---

# Finance amendment validation closeout

## Purpose and boundary

This records the completed test-environment validation of the finance-amendment slice in formal
specifications `06`, `14`, `16`, and `22`. It is not a production-release, deployment, or payment
execution record.

## Approved validation scope

2026-08-11: the user approved the Finance Amendment test-validation scope documented in Work
Package `55`. The system does not execute an accountant transfer; it only produces payable details
and later reconciles canonical bank facts.

## Verified readiness evidence

- Work Package `55` is completed and the focused cross-contract plus governance suite records
  `82 passed, 2 skipped`.
- Fresh disposable-MySQL cases prove replay, conflicting idempotency keys, row locking, and a
  two-connection competing government disposition.
- `scripts/verify_validation_schema_manifest.py` and
  `scripts/build_validation_schema_release.py --check` passed locally.
- The registry requires every active finance definition to declare a complete descriptor set or
  `no_automated_recovery=true`; former unmatched client/staff collection endpoints return typed
  `410` and point to matching-based replacements.
- `entrypoint_review_queue_v1.jsonl` has no unreviewed records after its latest validator run.

## 2026-08-11 local preflight record

The local schema-manifest and generated-release consistency checks passed. The artifact hashes,
commands and exact boundary are recorded in
`../receipts/2026-08-11_finance_amendment_release_preflight_receipt.md`.

That artifact is deliberately restricted to isolated `lu_test_*` databases. It proves that the
validation release can be rebuilt from version-controlled schema inputs; it is not a production
schema-release artifact and has not been applied anywhere.

On 2026-08-11 it was also applied to the existing isolated test schema
`lu_test_dataset_contract_signing_v4`. The postcheck passed and the WP 55 core focused regression
recorded `56 passed`. This is test-environment execution evidence only.

## 2026-08-11 UI-operable validation

The finance-amendment slice is also operable in the UI on a fresh isolated test schema
`lu_test_finance_ui_20260811`. In **異常警示中心 → 帳務異常**, an active `GOVSUB-006` was selected,
the typed **處置政府補助溢撥** action was opened, and the **建立政府退款應付** path completed both
Preview and Apply. The UI displayed a 500 NTD disposition and successful completion; the resulting
test root state is `return_payable` with one refund-payable detail. This is the user-testable UI
acceptance evidence for that government-overpayment vertical slice, not a production deployment or
bank-transfer instruction. The detailed receipt is the local preflight receipt above.

The focused Finance Amendment suite was rerun for UI-test closeout on the existing isolated test
schema and completed with `56 passed in 4.86s`. This closes the approved test-environment
acceptance scope of this package. No production target was selected or touched.
