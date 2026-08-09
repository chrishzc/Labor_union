---
doc_type: gap-package
declared_status: "proven"
---

# Durable Job Staff Payout Work Package

## Completed implementation boundary

The three Staff Payout Apply endpoints (`payout`, `return`, `reversal`) now
persist one versioned `staff_payout_apply` command envelope rather than placing
the request-scoped application connection in FastAPI `BackgroundTasks`.

The independent worker opens a fresh connection and reconstructs the existing
typed `StaffPayoutApplyRequest`. It preserves event type, canonical bank fact
identities, obligation identities, reopen fact identity, expected versions,
Preview fingerprint, idempotency key, actor, reason and correlation identity.
The existing Staff Payout reconciliation workflow remains the only UoW owner.

Retryable typed availability errors and MySQL lock/deadlock failures requeue;
other typed workflow errors remain terminal job results. The endpoint paths,
`202` response and job-status URL are unchanged. No UI, deployment, worker
supervision, schema or data migration changed.

## Current evidence

`tests/test_staff_payout_durable_job.py`,
`tests/test_staff_payout_reconciliation_workflow.py`, and
`tests/test_durable_job_worker.py` passed: 12 tests. They prove all three
event payload identities, fresh-connection request reconstruction and worker
registry ownership.

## Remaining proof

An isolated MySQL crash/replay E2E remains required. Its fixture must create
the canonical Finance Import outgoing bank fact, staff payable obligation,
primary staff bank account and, for return/reversal, the prior payout event
chain. A simplified row fixture would not prove source eligibility,
foreign-key behavior or the ownership transaction, so this package does not
claim Global durable-job completion.
