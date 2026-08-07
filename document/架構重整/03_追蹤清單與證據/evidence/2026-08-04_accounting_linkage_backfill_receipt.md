# Accounting Linkage Backfill Receipt — 2026-08-04

## Scope and isolation

This verification used only the disposable MySQL database
`lu_test_accounting_linkage_20260804` on its isolated test port. It did not
read from or write to `union_db`.

The pre-apply backup is a native MySQL dump (not a Windows UTF-16 redirected
text file):

| Artifact | SHA-256 |
|---|---|
| `lu_test_accounting_linkage_20260804.pre_backfill.native.sql` | `23f6974083fc65b9030a570f5c9aa73dfe7c1bf78d854ec83ad44bf2e8ec8782` |
| `dry_run_subsidy_state_machine_r2.json` | `ad333aa296c125b89a1a696c5d94260df590f8691db8f5bf52ba5cda464af576` |
| `apply_subsidy_state_machine.json` | `c021d84dd9cb22a8ede612ab490b4e2b7225be2428d6bb43b8c211dd054d4432` |
| `verify_subsidy_state_machine.json` | `ad19357dd601651294310de495f8a9e826aacb97129da3a0e5fb7e74520b0db6` |

## Policy facts verified

- `低收入戶` and `中低收入戶` normalize to the approved `補助市民` 120-hour policy.
- A subsidized client's staff-service rate and government claim unit rate are both
  NTD 350 per hour. Government coverage is capped at 120 hours; the client is
  charged NTD 350 per hour from hour 121 onward. This preserves the service-pay
  funding identity: `government coverage + client excess charge = staff service salary`.
- A full-subsidy order requires the policy qualification, service hours no
  greater than 120, and zero floor fee or other client self-pay amount.
- A positive derived client payable amount gives the staff payable the next
  calendar month's fifteenth; only a zero-payable full-subsidy order gets the
  second calendar month's fifteenth.
- A subsidized order over 120 hours without an explicit customer excess-hour
  rate is blocked rather than silently projected as a zero amount.

## Backfill result

The dry-run plan fingerprint was
`00ce6489d68a03cb756ae296d459c16254bbdcf015c2686de54117d682224b51`.

| Projection | Result |
|---|---:|
| Current open client receivables | 80 |
| Client rows requiring review | 2 |
| Current open staff payables | 12 |
| Staff rows requiring review | 3 fractional rows only |

Apply committed and a follow-up verify completed. The verify receipt has a
different dataset fingerprint because its `existing_counts` records the now
materialized canonical projections; this is expected and not plan drift.

## API/UI data-flow smoke

With the same isolated database and development-auth bypass used only in the
test process:

| UI path | Typed API result |
|---|---|
| 應付帳款查詢／輸出, September 2026 | `GET /api/v1/finance-reports/accounts-payable?target_month=2026-09` returned HTTP 200, 12 canonical staff-payable rows, total NTD 756,000. |
| 客戶收款核銷, case `115000001` | `GET /api/v1/orders/115000001/client-finance/receipt-reconciliation` returned HTTP 200, 3 canonical open obligations and 0 unreconciled bank facts. |

Both checks use canonical `staff_obligations` / `client_obligations`; neither
uses `client_payments.subsidy_refund_*`. Those legacy fields remain projection
only and are excluded from the formal accounting fact path.

## Refund and subsidy-advance runtime checks

On a separate empty `lu_test_refund_e2e_20260804` database, the following
isolated MySQL scenarios passed:

- an ambiguous customer-refund return creates one `CLIENTREFUND-001` review
  event and anomaly, with no automatic `refund_reversal`;
- a first-quarter subsidy payout creates `subsidy_advance` when its government
  allocation is absent at the fixed due date, then a later full government
  allocation creates one recovery link and no second customer payout;
- a partial government allocation creates review rather than automatic netting.

The final policy-state-machine suite passed 39 tests after the NTD 350 policy
rate correction. Finance Import then passed all 18 isolated MySQL E2E cases,
run in bounded groups because a single long pytest invocation can exceed the
Windows test-host process limit. The combined evidence includes root-fact
ingestion, correction, durable worker apply, refund return, G08/G10/G11,
subsidy advance and recovery; it does not claim that a bank row with no
immutable case evidence may be auto-dispatched.
