---
doc_type: gap-package
declared_status: completed
date: 2026-08-11
owner: finance-architecture
---

# Finance amendment executable contracts work package

## Business scenario

Administrators must record an actual bank amount exactly once when a client refund, staff payout, or government subsidy receipt differs from its intended obligation. The resulting remaining receivable or payable remains auditable and is repairable only through the Anomalies typed recovery flow.

## Approved scope

This package implements the four approved contracts in formal specifications `06`, `14`, `16`, and `22`: client over-refund recovery collection and authorized adjustment; staff payout difference and staff recovery; government overpayment offset, return payable, and bank-statement reconciliation; and the typed Anomalies action registry/UI dispatchers.

## SSOT and invariants

- Client Finance owns `client_over_refund_recovery`; Staff Payables owns `staff_overpayment_recovery`; Government Subsidy owns `government_subsidy_overpayment` and its return payable.
- Anomalies only projects root facts and returns descriptors. It never derives money, selects a target, or writes a domain aggregate.
- Every Apply locks the canonical bank fact, relevant root facts, source versions, targets, receipt, and outbox in one outer Unit of Work. Preview is read-only.
- Every selected bank amount equals formal allocations plus a newly established recovery/return payable or an explicitly retained pending-review amount.
- 2026-08-11 latest human decision: every refund first becomes a refund bill and accounting detail. The system never orders or executes the accountant's transfer. A later canonical outgoing bank fact reconciles the bill by recipient and amount; the bill's due date/detail date is never a reconciliation predicate, so emergency pre-payment is supported.

## 2026-08-11 recovery matching decision

Human decision: use **recovery matching assignment** rather than extending Finance Import classification with a recovery target. Finance Import continues to own only canonical bank facts and their broad business classification. Client Finance and Staff Payables each own an immutable matching aggregate that binds one eligible incoming bank fact to one open recovery, together with the recovery/account versions used by the subsequent collection Preview/Apply. The Anomalies dispatcher may request and display this typed matching flow, but does not write the matching or any monetary aggregate itself.

## Explicit exclusions

No production database deployment, external payment execution, automatic deduction against future wages/receivables, or Git remote mutation is included.

## Acceptance

- Module and disposable-MySQL tests prove conservation, stale rejection, idempotent replay/conflict, and transaction rollback.
- Registry validation proves every active finance definition is explicitly `no_automated_recovery` or has a complete descriptor.
- UI dispatches only registered form-schema keys, performs Query → Preview → Apply, and fails closed for unknown versions.
- `db/schema.sql`, release metadata, evidence index, and this package are updated with the implemented slice; no schema is applied to a production database.

## Current gap

2026-08-11 的逐條稽核結果如下；此表描述 live implementation，不改寫 `06`、`14`、`16`、`22` 的核准語意。

| Contract | Current evidence | Gap / live-drift |
|---|---|---|
| Client over-refund recovery | collection and authorized adjustment have Domain candidates, MySQL persistence, version/idempotency receipts, Preview/Apply transport, and focused module/workflow tests. Each newly classified, eligible incoming bank row is a fresh Finance Import manual-review root; its typed client recovery-matching action creates an immutable one-bank-row-to-one-open-recovery binding without changing Finance Import facts. Matching outbox then projects `client_over_refund_recovery_open`, whose dispatcher action calls only the matched collection endpoint; a full matched collection projects closure. | No known gap in approved scope. Partial collection requires a distinct newly classified incoming row and a new matching; consumed rows cannot be reused. The former unpaired collection endpoints are typed `410`, with matching and matched collection recorded as the replacement. |
| Staff payout difference and recovery | difference Apply creates immutable `payout_difference_identity` roots with FK-backed complete bank-row／obligation sets as post-Apply audit/replay evidence. Each newly classified eligible staff-return incoming row is a fresh Finance Import manual-review root and enters the typed matching Preview/Apply. `payout_anomaly_required` is consumed into state-only `staff_payout_underpayment`／`staff_payout_overpayment` alerts, whose predicates read current remaining payable／recovery state. Fresh disposable-MySQL cases prove payout, return, and reversal durable duplicate/crash recovery. | No known gap in approved scope. The dedicated post-Apply alerts deliberately have no second Apply because their source bank rows are consumed; partial recovery waits for a new matching. The former unpaired collection endpoints are typed `410`. |
| Government overpayment | receipt-overage, offset, return payable, next-payment-detail source, and later outgoing-bank reconciliation have typed Domain/workflow contracts; return snapshot fresh-reads payer account master; the finance-manual-review dispatcher binds the selected canonical outgoing row and the UI uses Preview/Apply reconciliation. Dedicated MySQL tests prove offset, return payable, early outgoing-row reconciliation, exact idempotency replay, and mismatched key rejection. `GOVSUB-007` now scans a uniquely matched government outgoing row whose amount exceeds the open return-payable remaining amount, and projects a state-only immutable review fact. | Recipient-account history is verified and due date is excluded. `GOVSUB-007` correctly performs no automatic settlement, offset, new payable, or payment execution; a separately approved money-disposition command would still be required to resolve the excess. |
| Typed Anomalies dispatcher | `GOVSUB-006` plus the Finance Import manual-review dynamic actions for client receipt/refund overage, staff payout difference, recovery matching, and government return reconciliation are typed schema-key dispatches. Client refund underpayment now has an immutable source and stateful projection. The Finance Import manual-review root is the current-query entry for every newly classified candidate bank row; root-fact recovery bindings are rehydrated from the current typed projection snapshot before registry action assembly, so owning-Domain version bindings survive the MySQL query boundary. Every active finance definition now explicitly declares either a complete descriptor set or `no_automated_recovery=true`; the registry rejects an implicit or contradictory state. | No known gap in approved scope. Stateful client/staff post-Apply alerts deliberately do not re-Apply their consumed bank rows. |
| Schema/release chain | additive parts `167`–`178`, recipient-account snapshot and client-refund-underpayment source lineage, manifest count/digest, and generated full release are aligned; source facts and government return-payout/apply receipts are append-only at the database boundary. Fresh disposable schemas exposed and corrected four missing trigger headers, the client-underpayment outbox enum, the government return-reconciled event enum, and the paid-zero return-payable constraint. | no known schema-chain gap in this scope. |
| Acceptance evidence | focused Domain/workflow/schema tests cover selected slices, including client refund underpayment projection, `GOVSUB-007`, rehydrated MySQL recovery bindings, typed UI routing boundaries, state-only registry declaration, typed `410` collection retirement, and entrypoint review queue validation. Fresh disposable-MySQL runs cover client recovery/overage, staff payout/return/reversal durable replay, government receipt durable replay, government overpayment offset/return/reconciliation replay, and two-connection competing Apply. The isolated Streamlit panel and an interactive browser session both exercise projector root → typed recovery action → real HTTP Preview → Apply. | Final cross-contract plus governance regression completed: `82 passed, 2 skipped`; separate disposable-MySQL scenarios are recorded in the receipt. |

All acceptance items above have focused evidence. `GOVSUB-007` remains state-only by design until a separately approved money-disposition command exists; that separate command is outside this completed package.
