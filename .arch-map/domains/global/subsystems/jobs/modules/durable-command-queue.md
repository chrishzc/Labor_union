# Module: durable-command-queue

## Parent
- domain: `global`
- subsystem: `jobs`

## Responsibility
保存 immutable command equality，協調 enqueue／claim／terminal transition 各自的 outer transaction，提供不含 raw handler payload 的公開結果。

## Implementation
- primary: `subsystems/jobs/contracts.py`、`subsystems/jobs/command_application.py`、`subsystems/jobs/durable_job_worker.py`
- persistence: `infrastructure/mysql/background_job_repository.py`
- transport: `api/routes/jobs.py`、`api/schemas/jobs.py`

## Contracts
- `document/架構重整/01_規格基線/00_Global_共同契約.md` §2.1。
- Public failure category 沿用 `shared_kernel/errors.py:ErrorCategory`；closed schema 拒絕額外 raw receipt／error 欄位。

## Verification
- layout_status: `custom_current`
- layout_basis: 沿用既有公開 job route oracle；本輪驗證 canonical producer 的各類 typed failure 皆可安全回讀，沒有搬移既有測試。
- test_root: `tests/test_jobs_public_outcome_route.py`

## Change triggers
Reconcile when command equality、queue transaction、terminal outcome、public transport 或 focused test root changes.
