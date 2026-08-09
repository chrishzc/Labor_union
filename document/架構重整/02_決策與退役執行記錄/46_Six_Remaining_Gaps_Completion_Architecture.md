---
doc_type: architecture-decision
status: approved-for-implementation
authorization_request_date: 2026-08-08
approved_by: user
approval_date: 2026-08-09
---

# Six Remaining Gaps Completion Architecture

## Completion boundary

This package covers the six remaining goals named by the user. It replaces no
root fact: manual bank-statement import remains the only payment-result fact.
An overdue item is a human reconciliation reminder, never a payment command or
a bank failure state.

## Global → Domain → Subsystem → Module

| Goal | Global responsibility | Domain SSOT | Subsystem | Module completion evidence |
|---|---|---|---|---|
| Writer Inventory | Every production writer has one accountable owner and a final disposition. | v3 candidate evidence plus disposition records. | Inventory reconciliation and validation; LINE user lifecycle. | Scan roots are a v1 superset including `services`; every unique identity is covered; `migrate_then_remove` has caller-free/Gone/removal receipt. LINE follow/unfollow, role change and onboarding cancellation share one transaction with the webhook event receipt. |
| Client refund | Imported outgoing bank fact is the sole settlement result. | Client obligation events, ledger and allocations. | Refund Preview/Apply and anomaly projection. | `CLIENTPAYABLE-001` is a read-only overdue reminder; UI links to the existing case and Finance Import review flow. |
| Subsidy return / union advance | No automatic payment or settlement. | Client `subsidy_return` obligation; Government Subsidy funding and claim allocation facts. | Advance-due root-fact consumer and anomaly projection. | `RETURN-001` covers overdue client payout; a separate `subsidy_advance_due` reminder is derived from funding facts and exposes a read-only review queue. |
| Scheduling / Payroll exit | Legacy mutation must not bypass typed ownership. | Scheduling assignment/service-date facts; Payroll obligations/ledger. | Inventory exit assertions. | Each legacy path is absent, returns Gone, or has no production caller; typed owner is the only writer. |
| Orders Query | All list reads are bounded and all case detail fields are intentional. | Orders and assignment projections. | Summary keyset query and typed detail query. | Orders and Scheduling preserve cursor history/next cursor; complete case detail has typed schema, authorization, repository and router tests; no runtime fallback to full list. |
| Global readiness | UI is a replaceable display layer and command identity is stable through retries. | Server-owned command/job state. | UI operation-state adapter and durable-job status query. | Idle/loading/success/empty/stale/error state, request supersession, same-command single-flight and bounded polling have tests. Deployment evidence separately proves TLS/HTTP2/latency/worker recovery. |

## State and transaction rules

1. An obligation is `open` or `settled`; only `open`, positive, past-due balances
   project reminders. A canonical bank import and successful allocation changes
   the projection; the next scan auto-resolves the reminder.
2. Client refund, subsidy return and union advance remain separate money flows.
   They never share a ledger entry type or infer a bank outcome from elapsed time.
3. All client-facing mutations use Preview/Apply, expected version, stable
   idempotency key and one owning transaction. Streamlit never implements a
   business fallback.
4. A retired writer must be unreachable before it is marked exited. Inventory
   labels alone are not exit evidence.
5. Bounded reads use a stable keyset cursor and page size at most 200. Old
   responses cannot overwrite newer UI request generations.
6. LINE user lifecycle has `active` and `blocked` states. A follow activates the
   user and creates idempotent welcome/onboarding tasks; an unfollow blocks the
   user and cancels only pending onboarding tasks. Refollow may cancel and
   recreate onboarding tasks only when the approved schedule enables it. The
   event receipt, state transition and task changes are one transaction.

## Delivery order and acceptance

1. Finish inventory reconciliation plus explicit Scheduling/Payroll/LINE exit
   receipts; retire only the paths proved unreachable.
2. Finish finance alert review queues and thin UI loading/state handling.
3. Deliver Orders cursor pagination and typed complete-detail read model.
4. Apply the shared UI operation-state adapter to durable command workspaces.
5. Run target-host deployment acceptance: TLS reverse proxy HTTP/2, optional
   HTTP/3 evaluation, latency smoke, Task Scheduler installation and queued-job
   recovery drill. These are external operational gates, not code-only claims.

## Confirmation

The user approved this architecture on 2026-08-09. Target-host deployment
steps are explicitly deferred while LINE remains in local development. They
remain a release gate, not a local-development blocker, and require the
operator to provide the host, reverse-proxy/certificate ownership and a safe
disposable acceptance environment before release acceptance begins.
