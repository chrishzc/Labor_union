# Client Refund Completion Decision Package

## 2026-08-04 live gap evidence

- Deterministic amount-conserving partial allocation is now implemented and has focused tests;
  an outgoing bank fact may settle a refund obligation from `pending` to a remaining balance.
- Finance Import has distinct `client_refund` and `client_subsidy_return` classifications,
  identity maps and owning-composite branches. The retired legacy subsidy-return dispatch fails
  closed rather than writing legacy projection fields.
- Automatic `client_refund` resolution requires an exact `case_no` in the immutable bank
  references. A unique refund account alone is not case authority. Without that source evidence,
  the row remains manual review; an operator may only proceed through the typed Correction
  selection with exact open obligations, reason, and evidence.
- Refund return/reversal foundations and focused tests exist. They are **not** sufficient for
  completion: isolated-MySQL real-format Excel E2E, canonical anomaly/work queue, Global
  scenarios and a publishable preserve-data release are still missing.
- A disposable MySQL 8.4 E2E now proves a real Taishin workbook can enter as immutable bank
  facts, open a canonical manual-review alert, and—after typed manual correction—create a
  `refund` ledger entry, exact allocation, settled obligation, correction outbox, and resolved
  anomaly. This covers manual refund correction only; return/reversal and Global scenarios remain
  incomplete.
- Client subsidy return remains a separate payable line. The legacy module
  `subsystems/client_finance/subsidy_return_reconciliation.py` has been retired after a
  full runtime/maintenance caller scan proved zero callers; its three projection writers no
  longer exist and must not be reintroduced as a compatibility path.
- A subsidy payout is no longer always recorded as `subsidy_return`. When its single
  linked claim item has no Government receipt allocation, the actual completion date is
  in the first month of its claim quarter, and the outgoing bank fact is on or after the
  fixed due date, Finance Import records `subsidy_advance`. A full later allocation creates
  exactly one recovery link; a partial or otherwise mismatched allocation opens review and
  never creates a second client payout. This has both focused and isolated-MySQL evidence.

## Formal completion scope

1. Replace equal-total refund allocation with deterministic amount-conserving allocation that permits `pending → partially_refunded → refunded`.
2. Add immutable refund return and refund reversal commands that reopen the exact remaining refund obligation; never update/delete a prior ledger entry.
3. Add Finance Import `client_refund` classification, unique case/obligation resolution and borrowed Client Finance outer UoW dispatch. Ambiguity must fail closed to review.
4. Add canonical refund anomaly projection and global work-queue routing for allocation mismatch, return/reversal conflict and bank ambiguity.
5. Update Accounts Payable Export to emit customer refund separately from subsidy return, using remaining refundable amount only.
6. Add module, subsystem, isolated MySQL Domain and Global E2E tests for partial refund, full settlement, refund return, refund reversal, replay/mismatch/stale, dispatch ambiguity and rollback.

## Non-negotiable invariants

- A bank outflow is fully allocated or rejected; no unallocated amount remains.
- Multiple valid outflows may settle one obligation, but cumulative valid refunds cannot exceed the immutable obligation amount.
- Refund, subsidy return and receipt reversal remain distinct commands and ledger event types.
- No negative receipt, no original receipt rewrite, no cross-case offset and no Orders lifecycle rollback.
- Apply has one Client Finance outer UoW, expected version, preview fingerprint, idempotency receipt and committed outbox.

## Acceptance evidence

- Real-format Excel in an isolated disposable MySQL database proves ingestion → classification → Preview → Apply → Client Finance ledger/projection → Anomalies.
- Global E2E proves customer refund and Staff Payables payout coexist without netting.
- Writer Inventory v3 records the resulting canonical writers and proves no legacy refund caller remains.
