---
doc_type: contract
declared_status: completed
date: 2026-08-08
---

# LINE Ingress Developer Experience Convergence Contract

## Audience and agent entrypoint

This contract is primarily for development agents and developers entering the
LINE scope. Read it before changing `line/line_bot.py`, `line/worker.py`, or
`subsystems/line/**`. It is the short operational entrypoint for deciding
where a new LINE capability belongs; the owning Domain baseline remains the
authority for the business rule itself.

An agent must use this sequence rather than infer behavior from existing
direct SQL handlers:

```text
identify intent -> identify owning Domain -> reuse/add typed command
-> add registry entry -> add acceptance evidence -> migrate one legacy handler
```

This document does not authorize a UI change, a schema change, or deletion of
a legacy handler. It prevents a convenient-looking LINE edit from becoming a
new unowned business writer.

## 1. Decision

LINE Integration is an external-channel adapter, not a business Domain owner.
It must be easy to extend without allowing `line_bot.py` to write business
tables or to encode a Domain state machine. A new LINE capability follows one
short, repeatable path:

```text
verified webhook event -> deduplicated inbox -> intent registry -> typed Domain command
-> Domain Preview/Apply transaction + receipt + outbox -> durable LINE delivery task -> worker
```

The adapter may parse a user message and choose a capability. It must not
decide a business transition, calculate a business result, or issue SQL against
`orders`, matching, client, finance, payroll, or other Domain tables.

## 2. Fixed responsibilities

| Component | May do | Must not do |
|---|---|---|
| Webhook ingress | Verify LINE signature, persist the raw event once, normalize transport fields, and create a typed intent. | Mutate Domain tables, send a reply synchronously, or infer a business state from raw SQL. |
| Intent registry | Map a stable intent name to its owning Domain command factory and response mapper. | Contain SQL, Domain policy, or a second state machine. |
| Domain workflow | Preview and Apply the command; own validation, locks, idempotency, typed errors, receipts, and Domain outbox facts. | Call LINE APIs. |
| Delivery task workflow | Persist a deterministic delivery task after the owning transaction succeeds. | Re-run a Domain transition. |
| LINE worker | Claim a due task, call the LINE API after commit, record delivery outcome, and retry safely. | Alter Domain state to compensate for a delivery failure. |

`webhook_inbox.py`, `delivery_task_workflow.py`, and `worker.py` remain the
shared transport primitives. The legacy direct writes in `line_bot.py` are
migration sources only; they are not templates for new features.

## 3. Capability extension template

A developer or agent adding a LINE capability must complete only these steps:

1. Reuse an existing typed Domain command, or add one inside its owning Domain.
2. Add one intent-registry entry: intent name, command factory, and response
   mapper.
3. Add the Domain Preview/Apply test covering success, stale/conflict, and
   idempotent replay.
4. Add one adapter test proving the webhook event creates the intended command
   and no direct Domain SQL is issued.
5. Add one delivery-task test proving success and retry do not duplicate the
   user-visible reply.

The registry is the discovery surface for future developers. It must document
the owning Domain and the typed request/response type beside each capability;
no reader should need to search database tables to add a normal message flow.

## 4. Migration rule

Each current `line_bot.py` direct mutation is migrated one capability at a
time. The replacement must preserve the existing user-visible intent while
moving the state transition into the owning Domain workflow. Direct
`INSERT line_tasks` becomes `enqueue_line_task`; direct updates to client,
matching, order, or import records become typed Domain commands.

Before changing a handler, add characterization pytest coverage for its live
legacy behavior. The test must record the accepted payload, the resulting
business state, the queued reply, idempotent redelivery, and invalid or stale
input behavior. This baseline is required before a replacement test is added;
the refactor is not accepted merely because its new workflow tests pass.

No handler is deleted until its replacement has an independent workflow and
adapter acceptance test. Delivery side effects are never part of the Domain
transaction: a committed Domain receipt plus a durable task is the boundary.

## 5. Required invariants

- A redelivered webhook cannot apply the same Domain command twice.
- A stale or conflicting Domain command returns its typed error; it does not
  produce a compensating direct SQL update from LINE.
- The same logical reply has one deterministic delivery task identity.
- A worker retry can resend only according to the delivery task retry policy;
  it cannot repeat the Domain mutation.
- A delivery failure does not roll back a completed Domain command.
- The adapter has no business-table writer except the inbox and delivery-task
  transport stores.

## 6. Acceptance evidence before legacy exit

1. Pre-migration characterization pytest for the legacy handler's payload,
   resulting state, reply task, replay, and failure behavior.
2. Webhook signature, duplicate-event, intent-resolution, and malformed-input tests.
3. Domain success, stale/conflict, idempotent replay, and authorization tests.
4. Transaction test proving receipt and delivery task commit together.
5. Worker claim/retry test using concurrent claim semantics.
6. Static inventory check showing no `line_bot.py` direct business-table update
   or direct `line_tasks` insert remains.
7. A developer-facing registry example covering one complete capability from
   inbound message to delivered reply.

This contract changes the future development path, not the existing LINE
behavior. Production migration requires a separate approved implementation
package and must stop for any UI change.


## Legacy postback retirement decision

Confirmed decision: legacy LINE postbacks with only `case_no` and `staff_id` are accepted for webhook deduplication and a retirement notification only. They must not update `matching_records`, `orders.client_approved`, schedules, assignments, or any other business state.

The retired actions are `willing`, `unwilling`, `client_approve`, and `client_reject`. New business mutations require the canonical identity required by the owning workflow; matching willingness requires `plan_id` and `segment_id`. New message producers must never emit the retired payload shapes.
