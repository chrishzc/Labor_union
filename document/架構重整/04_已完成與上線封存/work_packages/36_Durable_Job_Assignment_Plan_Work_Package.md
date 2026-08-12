---
doc_type: gap-package
declared_status: "implementation-complete; isolated-mysql-e2e-proven"
---

# Durable Job Assignment Plan Work Package

## Purpose

This work package narrows the durable-job completion gap to one command:
`Assignment Plan Apply`. The user authorized the server-side implementation
and isolated-MySQL tests. UI, deployment configuration, worker supervision,
and schema/data operations remain out of scope.

## Why this first slice

Assignment Plan is a long-running, non-atomic orchestration candidate. Its
current route returns `202 Accepted` but starts its worker using FastAPI
`BackgroundTasks`; a web-process restart can therefore leave the accepted job
without an independent consumer. The existing Finance Import durable queue is
the reference envelope and worker model. Assignment Plan business rules and
its outer Unit of Work must remain in the existing owning application.

## Proposed implementation boundary

- Reuse the existing versioned durable command envelope and lease/retry queue;
  do not create a second queue table.
- Register one Assignment Plan handler that reconstructs the existing typed
  Apply command and calls the current owning application/UoW.
- Change only the Assignment Plan Apply route from API-process
  `BackgroundTasks` execution to durable enqueue.
- Preserve idempotency identity, actor, correlation id, Preview fingerprint,
  typed errors, receipt reference, and Jobs status response fields.
- Do not alter Assignment Plan Preview, Matching UI, job polling UI,
  cancellation API, worker supervision, deployment, or any other command.

## Required tests before route migration

1. Module: handler payload serialization/deserialization and typed error
   serialization.
2. Subsystem: enqueue replay, claim race, expired lease recovery, retry, and
   terminal receipt ownership with a disposable MySQL schema.
3. Domain: a queued Assignment Plan Apply produces exactly the same canonical
   assignment, occupancy, scheduling, finance, payroll, lifecycle, and
   receipt facts as its synchronous equivalent.
4. Global: API timeout followed by same-key retry cannot produce duplicate
   Apply facts; a worker crash before completion remains retryable.

## Rollback

Rollback stops new Assignment Plan queue submissions and restores the route's
previous execution path only after queued records are drained or terminally
failed with typed errors. It must retain queued command envelopes and all
domain receipts/facts.

## Implementation evidence

- The Assignment Plan Apply route now writes a versioned
  `assignment_plan_apply` durable command envelope and returns its existing
  `202 Accepted` job response without scheduling a FastAPI `BackgroundTasks`
  callback.
- The independent durable worker reconstructs the existing typed Apply request
  with a fresh MySQL connection and invokes the existing Assignment Plan
  application/UoW. It preserves idempotency key, actor, correlation id,
  Preview fingerprint, all expected versions, segments, and official service
  dates.
- `tests/test_assignment_plan_durable_job.py`,
  `tests/test_durable_job_worker.py`, and
  `tests/test_assignment_plan_workflow.py` passed: 12 tests.
- `tests/test_assignment_plan_durable_mysql_e2e.py` passed against a fresh,
  disposable `lu_test_assignment_plan_durable` MySQL schema: 1 test. It proves
  same-key API replay creates one durable job, an expired worker lease is
  recovered by an independent worker, the command succeeds on attempt two,
  and exactly one Assignment Plan Apply receipt is persisted.

## Completion boundary

The isolated-MySQL crash/replay and same-key duplicate-delivery proof is
complete. UI, deployment configuration, worker supervision, and schema/data
operations remain explicitly out of scope for this work package.
