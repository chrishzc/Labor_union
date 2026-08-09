---
doc_type: gap-package
declared_status: "implementation-complete; isolated-mysql-e2e-proven"
---

# Durable Job Payroll Rebuild Work Package

## Purpose

Payroll Rebuild Apply previously returned `202 Accepted` after placing a
closure that held the request-scoped application connection in FastAPI
`BackgroundTasks`. A web-process restart could therefore leave a persisted
job without an independent consumer. This package moves only that Apply
command to the existing versioned MySQL durable queue.

## Implementation boundary

- The public Preview endpoint, Apply endpoint path, `202` response, job-status
  URL, typed request shape and UI contract are unchanged.
- The route now persists one `payroll_rebuild_apply` envelope containing the
  case, expected payroll version, Preview fingerprint, idempotency identity,
  actor, reason and correlation identity.
- The independent worker opens a fresh connection, reconstructs the existing
  typed request and invokes the existing Payroll Rebuild application/UoW.
- Retryable repository or MySQL availability failures requeue; stale Preview,
  validation and domain errors remain terminal typed job results.
- No UI, deployment, worker supervision, cancellation API, schema migration
  or data migration is included.

## Evidence

- `tests/test_payroll_rebuild_durable_job.py`,
  `tests/test_durable_job_worker.py`, and
  `tests/test_payroll_rebuild_workflow.py` passed: 12 tests.
- `tests/test_payroll_rebuild_durable_mysql_e2e.py` passed against a fresh,
  disposable `lu_test_payroll_rebuild_durable` MySQL schema: 1 test. It builds
  canonical payroll facts through the existing Assignment Plan application,
  proves same-key API replay creates one durable job, recovers an expired
  worker lease, succeeds on attempt two and persists exactly one
  `payroll_apply_receipts` row.

## Completion boundary

The isolated-MySQL crash/replay and same-key duplicate-delivery proof is
complete. Payroll Rebuild remains owned by its existing workflow and outer
Unit of Work; this package does not authorize changes outside the boundary
above.
