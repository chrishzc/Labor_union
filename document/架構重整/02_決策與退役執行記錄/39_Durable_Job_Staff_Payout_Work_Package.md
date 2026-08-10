---
doc_type: gap-package
declared_status: "implementation-complete; isolated-mysql-e2e-proven"
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

## Isolated MySQL crash/replay proof

`tests/test_staff_payout_durable_mysql_e2e.py` now creates the canonical
Finance Import outgoing/incoming bank facts, staff payable obligation, primary
staff bank account and the prior payout chain needed by return/reversal. The
2026-08-09 disposable MySQL 8.4 run passed all payout, return and reversal
durable replay cases; its Payroll-domain receipt is
`03_追蹤清單與證據/evidence/2026-08-09_payroll_domain_revalidation_receipt.md`.
This proves source eligibility, foreign-key behavior, fresh-connection worker
reconstruction, same-key replay and expired-lease recovery without claiming
target-host worker supervision or deployment acceptance.
