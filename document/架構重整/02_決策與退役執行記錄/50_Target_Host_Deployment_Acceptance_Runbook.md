---
doc_type: operational-acceptance-runbook
status: awaiting-target-host-execution
date: 2026-08-09
---

# Target-host Deployment Acceptance Runbook

This runbook is evidence collection, not a local-development substitute. Run it
only on the approved target host with a disposable acceptance command and a
private/disposable database environment.

## Preconditions

- Record the host owner, edge/reverse-proxy owner, TLS certificate owner and
  private administrator access path.
- Confirm MySQL is private and no acceptance command points to `union_db` or
  any production database.
- Confirm the Windows `SYSTEM` account can read the project directory and the
  protected `.env` without exposing secret values in output.

## Edge and protocol evidence

1. Configure the managed edge/reverse proxy to terminate TLS and forward only
   to the local application listener. Do not expose MySQL or the Streamlit
   admin interface publicly.
2. From an authorised external probe, record certificate subject/expiry,
   negotiated TLS version, HTTP/2 negotiation and a successful HTTP/1.1
   fallback request. HTTP/3 is optional and must not change application
   semantics.
3. Record timestamped p50/p95 first-byte and total-latency measurements for a
   bounded query, one Preview and one accepted durable Apply. Retain request
   correlation IDs, not sensitive payloads.

## Durable worker recovery drill

1. On the target host, install the worker task from an elevated PowerShell:

   ```powershell
   .\scripts\install_durable_job_worker_task.ps1 -StartNow
   .\scripts\get_durable_job_worker_task_status.ps1
   ```

2. Create one reviewed disposable durable command using its fixed idempotency
   key. Once the worker owns its lease, terminate only the worker process.
3. Wait for the configured lease expiry/restart, then inspect job state and
   receipt. The command must execute exactly once; a retry with the same key
   must return the existing job/receipt rather than a second domain write.
4. Record Scheduler task state, worker log timestamps, durable job identity,
   final receipt identity and the database transaction evidence. Redact
   credentials, personal data and bank payloads.

## Acceptance record

The release evidence must contain: host/environment identifier, date/time,
operator, proxy protocol output, latency values, task status, recovery result,
idempotency replay result and any failed criterion. Absence of this record
keeps TLS/HTTP2/latency/worker-recovery as `external-gate`.
