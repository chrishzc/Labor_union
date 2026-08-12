# 2026-08-11 Finance amendment focused regression receipt

## Scope

This is local evidence for Work Package `55_Finance_Amendment_Executable_Contracts_Work_Package.md`. It is neither an approval nor a production deployment record. It records the completed disposable-MySQL cases and interactive-browser evidence below.

## Latest focused regression

```text
.venv\Scripts\python.exe -m pytest \
  tests/test_client_refund_underpayment_anomaly_projection.py \
  tests/test_client_refund_partial_allocation.py \
  tests/test_client_refund_overage.py \
  tests/test_client_receipt_overage.py \
  tests/test_client_over_refund_recovery.py \
  tests/test_staff_payout_difference.py \
  tests/test_staff_overpayment_recovery.py \
  tests/test_government_subsidy_overpayment.py \
  tests/test_government_subsidy_overpayment_workflow.py \
  tests/test_recovery_context_assembler.py \
  tests/test_finance_anomaly_recovery_ui.py -q
```

The final cross-contract focused suite additionally includes client/staff matching and their anomaly projections, the MySQL root-fact recovery-snapshot adapter, `GOVSUB-006`／`GOVSUB-007`, the government consumer, and the Streamlit government action boundary.

Result: `82 passed, 2 skipped`. The two skipped cases require an explicitly configured disposable MySQL database; their corresponding real disposable-MySQL cases are recorded below.

### Disposable-MySQL reconstruction matrix

The two skips are environment guards, not accepted omissions. In CI or a local operator run, set a
fresh database name matching `lu_test_*` in `LABOR_UNION_TEST_MYSQL_DATABASE`, provide the matching
`LABOR_UNION_TEST_MYSQL_HOST`／`PORT`／`USER`／`PASSWORD`, and run each test against a new empty
schema because the bootstrap intentionally refuses reuse:

```text
.venv\Scripts\python.exe -m pytest \
  tests/test_client_refund_recovery_disposable_mysql_e2e.py -q -p no:cacheprovider

.venv\Scripts\python.exe -m pytest \
  tests/test_finance_alerts_government_overpayment_ui_e2e.py -q -p no:cacheprovider
```

The first proves client refund underpayment recovery against an actual database. The second proves
the Streamlit typed government disposition Preview → Apply boundary. Both bootstrap the supplied
disposable schema and must never target production.

Post-audit governance regression additionally passed `15 passed`: active finance definitions now explicitly choose a descriptor set or `no_automated_recovery`; the former unmatched client/staff collection routes return typed `410`; and the complete entrypoint review queue has no `review_required` records.

The same change boundary also passed `compileall`, `scripts/verify_validation_schema_manifest.py`, `scripts/build_validation_schema_release.py --check`, and scoped `git diff --check`.

## Government outgoing-overage projector regression

```text
.venv\Scripts\python.exe -m pytest \
  tests/test_government_return_outbound_overage_anomaly_projection.py \
  tests/test_government_subsidy_overpayment.py \
  tests/test_government_subsidy_overpayment_workflow.py \
  tests/test_government_subsidy_overpayment_anomaly_projection.py \
  tests/test_government_overpayment_anomaly_consumer.py -q
```

Result: `16 passed`. `GOVSUB-007` is emitted only for a uniquely matched, open government return payable whose canonical outgoing amount exceeds remaining. It is state-only: no ledger allocation, offset, new payable, or payment execution occurs.

## Dispatcher recovery-binding query regression

Result: `10 passed` for the MySQL recovery-snapshot adapter, `GOVSUB-006`, client recovery bindings, and the fail-closed context assembler. The query now rehydrates the typed `recovery_bindings` object saved with the current root-fact projection before it attempts registry action assembly.

## Covered behaviour

- Client refund bills retain a recipient-account snapshot; subsequent canonical outgoing rows reconcile by recipient account and amount, never by bill, payment-detail, or bank-row date.
- A recorded client-refund underpayment writes immutable root, consumed-bank-row, and remaining-refund-obligation source facts. The original refund obligation remains the only payable; a later outgoing row must be newly selected and reconciled against that existing obligation.
- Client over-refund recovery, staff payout difference, staff overpayment recovery, government receipt-overage, offset, return payable, and later return reconciliation all retain their focused domain/workflow regressions.
- The typed Anomalies/UI boundary dispatches the registered Preview → Apply forms and keeps post-Apply state-only alerts from resubmitting already consumed bank rows.

## Disposable-MySQL evidence

The general bootstrap gate was repaired by correcting the stale source anchor for `CS-CONTRACT-SIGNING-001`; its authoritative target heading already existed. No finance rule was changed. Fresh, isolated `lu_test_*` schemas were then built from the complete additive release. The bootstrap exposed and corrected four schema trigger headers (staff recovery, client recovery receipt, recipient snapshot, and client-underpayment source) and the missing `client_refund_underpayment_required` outbox enum value.

The following real MySQL cases passed, each against a fresh disposable schema; no production database was contacted or changed:

- client recovery closed loop and partial/replay (`2 passed`);
- confirmed client receipt overage → immutable recipient snapshot → open refund payable (`1 passed`);
- staff payout, staff return, and payout reversal durable duplicate/crash recovery (`3 passed`, executed separately because the bootstrap intentionally refuses to overwrite a prior test schema);
- government subsidy receipt durable duplicate/crash recovery (`1 passed`).
- government overpayment offset, return payable, and early outgoing-bank reconciliation each replay exactly once; same idempotency key with a different command fails closed (`2 passed`).
- two independent MySQL connections concurrently applying the same government offset take the root lock before the receipt lock, both return the same durable receipt, and persist exactly one disposition (`1 passed`).
- typed Anomalies recovery selection → Streamlit government return-disposition Preview → real HTTP Apply (`1 passed`); the Apply creates an accounting return payable and never executes a transfer.

These runs prove schema application and the exercised transaction, row-lock, replay, and durable-worker paths, including the dedicated government offset/return-disposition path. The UI evidence includes the isolated Streamlit panel/real HTTP test and the interactive browser session below.

## Interactive browser evidence

Against the isolated `lu_test_finance_runtime_20260811` database, a real `GOVSUB-006` root was projected through `government_overpayment_anomaly_consumer`, displayed in Streamlit's Anomalies finance tab, and operated in the browser: typed action query → `建立政府退款應付` selection → Preview (500 / remaining 500) → Apply. The visible result was `已完成處置；剩餘 500 元。` The action only created the next accounting payable; no transfer was issued. The projector correction binds `finance_import_batch_id` from the canonical bank row rather than the unrelated subsidy claim batch.

## Explicit non-evidence / remaining verification

- No browser-session gap remains for the government typed action path. Other domain form variants remain covered by their focused UI/API tests.
- A government return reconciliation whose outgoing amount exceeds the selected return payable is fail-closed with `government_overpayment_return_outbound_amount_exceeded`; it remains in the existing Finance Import manual-review flow. There is no separate `government_overpayment_return_pending` projection in the current codebase, and this receipt must not claim one.
