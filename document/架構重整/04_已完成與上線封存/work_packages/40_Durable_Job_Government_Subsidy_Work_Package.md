---
doc_type: gap-package
declared_status: "proven"
---

# Durable Job Government Subsidy Work Package

## Decision

The five Government Subsidy Apply actions now persist one versioned
`government_subsidy_apply` command with an explicit action discriminator:
claim plan, claim submission, claim approval, receipt, and reversal.

The API still returns the existing `202 Accepted` receipt and job-status URL.
The worker opens a fresh MySQL connection and reconstructs the existing typed
request. Existing Government Subsidy claim and ledger workflows remain the
sole transaction and idempotency owners.

## Proven boundary

`tests/test_government_subsidy_durable_job.py`,
`tests/test_government_subsidy_claim_workflow.py`,
`tests/test_government_subsidy_ledger_workflow.py`, and
`tests/test_durable_job_worker.py` passed with 12 tests. They prove all five
payload variants reconstruct typed requests, the new worker handler uses a
fresh connection, and no Government Subsidy route retains FastAPI
`BackgroundTasks`.

## Remaining evidence

Disposable MySQL has proven claim planning, submission, approval, canonical
bank receipt, and receipt reversal crash/replay from official Assignment Plan
facts through the durable worker. Each action proves same-key queue de-duplication,
expired-lease recovery, a fresh worker connection, and one formal result.
