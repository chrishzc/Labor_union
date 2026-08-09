# Durable Job Worker Supervision Deployment Decision

## Decision

The approved `local-primary` deployment mechanism for the durable job worker is
Windows Task Scheduler. The task name is `LaborUnionDurableJobWorker`.

The task runs `scripts/run_durable_job_worker.py` with the project's virtual
environment Python under the `SYSTEM` service account. It starts at system
startup, permits only one worker instance, and restarts up to three times with
a one-minute interval after an unexpected process exit.

## Operational contract

1. The worker is a required process for every durable command. API acceptance
   does not mean the command has completed.
2. The task must be installed from an elevated PowerShell on the managed app
   host. The installation script never embeds database credentials; the worker
   reads the protected project `.env` file using its existing configuration.
3. `online.bat` remains an operator convenience and development fallback. It
   is not the production worker supervisor once the scheduled task is active.
4. The read-only status script reports Scheduler state and the latest task
   result. It does not run the worker with `--once`, because that could claim
   and apply a queued business command.
5. The durable queue remains the execution state SSOT. Scheduler restart and
   worker lease recovery must not create duplicate domain writes.

## Installation and recovery

```powershell
# Register only; the worker starts automatically at the next boot.
.\scripts\install_durable_job_worker_task.ps1

# Register and start immediately after a reviewed deployment.
.\scripts\install_durable_job_worker_task.ps1 -StartNow

# Inspect only; no business command is run by this check.
.\scripts\get_durable_job_worker_task_status.ps1

# Remove during a controlled rollback or decommission.
.\scripts\uninstall_durable_job_worker_task.ps1 -WhatIf
```

Installation requires Administrator privileges. Before production installation,
verify that `SYSTEM` can read the project directory and `.env`, and perform a
controlled queued-job recovery drill. Task registration artifacts prove the
deployment contract, but do not replace target-host installation evidence.
