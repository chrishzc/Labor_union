---
doc_type: decision-package
---

# Durable Job Completion Decision Package

## 1. Purpose and decision boundary

This package records the live durable-job gap against the approved Global
Performance and UX architecture.  It is evidence and an implementation plan;
it does not authorize a schema change, production-code change, deployment, or
data operation.

The target is a job whose queued state survives a web-process restart and is
claimed by an independently supervised worker.  Returning a `job_id` alone is
not sufficient.

## 2. Fresh source evidence

| Source | SHA-256 | Finding |
|---|---|---|
| `infrastructure/mysql/background_job_repository.py` | `F7FBBB608F682B083D53B4FC9D47DAC00FF38FA3C6686C2944ED8E6DD94C34FE` | Implements durable enqueue/read/claim, bounded lease recovery and terminal transitions for the first migrated command. |
| `db/schema_parts/137_background_jobs.sql` | `5D80D7026585CDDA00772723F6DCCCD53AA2CDD23BA8EE9B4C3DB35ADDB77718` | Persists identity, five statuses, payloads and timestamps only; it has no command payload, handler identity, attempt count, lease, worker receipt reference, or retry schedule. |
| `shared_kernel/background_jobs.py` | `CC719E3C44B0329382C89BA59970DAC26329EDAE9C5E18B26B8C08B87CB475A8` | Defines the intended lifecycle and queue port, but the MySQL adapter does not implement that port. |
| `api/routes/assignment_plan.py` | `3FD2609147E0AAA457211B39BDB62CF0131713042BBEDC8B4AA40773439FF572` | Enqueues then calls `BackgroundTasks.add_task`; the nested worker invokes the application command in the API process.  The same pattern is present in Finance Import, Payroll Rebuild, Staff Payout and Government Subsidy routes. |
| `api/routes/jobs.py` | `246173ADAFB05BFC6D04E417F5D9E955239D2C83021B774A4D0711807B21DAFD` | Provides the canonical `/api/v1/jobs/{job_id}` administrator-only `BaseResponse` status read with command, attempt and receipt fields; no push notification or cancellation endpoint. |

Fresh repository search found no production consumer which claims
`background_jobs` records.  The only `mark_running`, `mark_succeeded` and
`mark_failed` callers are API route-local background functions.

## 3. Current disposition

`partial` — the first real command path, `finance_import_batch_apply`, now
uses the additive `141_durable_background_job_queue.sql` envelope, MySQL lease
queue and `scripts/run_durable_job_worker.py`.  The worker reconstructs the
existing typed Finance Import Apply request with a fresh owning-domain outer
UoW; it does not duplicate Finance Domain rules.  The `/api/v1/jobs/{job_id}` status
view now reports command type, attempts and receipt reference with typed
`job_not_found`.

Finance Import correction, Assignment Plan, Payroll Rebuild, Staff Payout and
all five Government Subsidy Apply routes now use the same persisted command
envelope and independent worker as batch Apply. Each migrated Domain has
isolated MySQL crash/replay evidence. A typed cancellation endpoint now limits
the transition to still-unclaimed queued work. Worker supervision, deployment
startup, automatic bounded polling with backoff/jitter, and preserve-data
migration runner remain incomplete. Finance Import has only a user-triggered
one-request-per-click status refresh and same-key timeout retry.

## 3.1 2026-08-04 implementation evidence

| Proof | Result |
|---|---|
| `tests/test_durable_job_worker.py` | 4 passed: claimed-only completion, retryable error requeue, unknown-handler terminal failure and durable status fields. |
| `tests/test_background_job_repository_mysql.py` | 2 passed on `lu_test_finance_reprocess_20260804`: retry keeps command identity, a new lease token is issued, and expired lease recovery is claimable. |
| `tests/test_durable_finance_import_batch_e2e.py` | 2 passed on the same disposable MySQL: real Taishin workbook ingestion → durable queue → independent worker → existing typed Apply/UoW → succeeded receipt; and a lost API response retried with the same key still writes one job and one Apply receipt. |
| `tests/test_finance_import_disposable_mysql_e2e.py::test_durable_correction_worker_posts_manual_refund_once` | 1 passed on `lu_test_durable_correction_e2e_20260804`: a manual refund correction command is persisted, an independent connection claims it, writes one ledger plus one correction receipt, and a second worker pass is idle. |
| `tests/test_finance_import_historical_reprocess_ui.py` | 4 passed: Finance Import UI preserves the first Apply idempotency identity after a transport timeout and displays queued/running work as pending, not success. |
| `tests/test_g17_finance_import_ui_job_e2e.py` | 1 passed on dedicated disposable MySQL: panel response timeout → same-key retry → canonical jobs API queued read → independent worker → panel succeeded display. |
| API import smoke | `api.main` and the Finance Import durable command serializer import successfully. |

The known Windows `.pytest_cache` `WinError 183` warning did not prevent any
test body from executing and is not a durable-job result.

## 4. Required target contract

1. A typed durable command envelope stores command type, versioned payload,
   idempotency identity, actor, correlation id and submitted timestamp.
2. A MySQL queue adapter atomically claims one queued record with a bounded
   lease and attempt identity.  Only a holder of that lease may complete it.
3. An independently started worker dispatches the registered handler through
   the existing owning application command and outer Unit of Work.  It never
   reimplements Domain rules.
4. Expired leases become retryable under a deterministic retry policy.  A
   duplicate delivery keeps the same command identity and cannot duplicate a
   domain transaction.
5. `succeeded` stores the authoritative command receipt reference; `failed`
   stores a typed error; cancellation is limited to a still-unclaimed job.
6. The status API returns the approved accepted fields, a typed status view,
   and typed `job_not_found`, `job_state_conflict`, `job_queue_unavailable`,
   and `job_result_unavailable` errors.
7. UI polling is bounded with backoff and jitter.  The repository remains the
   state SSOT when notifications are lost.

## 5. Safe migration order

1. Add the versioned command-envelope and queue/lease data contract by a
   preserve-data migration, including an explicit rollback switch.
2. Implement the queue port, handler registry, worker, lease expiry recovery
   and typed status projection behind the new contract.
3. Add module tests for transitions, claim races, duplicate delivery,
   cancellation and error serialization.
4. Add isolated-MySQL subsystem tests for restart between enqueue and claim,
   crash during execution, lease expiry, retry and idempotent receipt replay.
5. Migrate one measured non-atomic long-running command at a time.  Core
   atomic Apply commands remain synchronous unless measurement proves the
   request budget is exceeded and the command can retain one outer UoW.
6. Add bounded UI polling only after the corresponding worker route is live.
7. Validate worker startup and supervision in the deployment package; do not
   claim deployment readiness from local FastAPI background tasks.

## 6. Rollback

The migration is additive.  Until a command route is switched, it keeps the
current execution path.  For a switched command, rollback stops new queue
submissions, drains or explicitly fails leased jobs with their typed error,
and restores that route to its previous synchronous implementation.  It must
not delete command records, receipts or domain facts.

## 7. Acceptance matrix

| Scope | Required proof |
|---|---|
| Module | Lifecycle transition, enqueue idempotency, lease ownership, cancellation and typed-error tests. |
| Subsystem | Isolated MySQL proves claim race, duplicate delivery, crash recovery, retry schedule and status reads. |
| Domain | A queued command produces exactly the receipt and root facts of its synchronous equivalent. |
| Global | Worker restart and notification loss do not duplicate a transaction or report a false success; supervisor and deployment evidence prove the worker is independently running. |

## 8. Authority still required

An implementation work package must explicitly authorize the additive schema
migration, the selected first command, worker process configuration and its
isolated-MySQL tests.  Deployment, production queue operation and any data
backfill remain separate authorizations.
