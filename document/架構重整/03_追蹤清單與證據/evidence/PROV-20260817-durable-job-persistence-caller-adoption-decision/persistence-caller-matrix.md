# Durable Job Option A persistence／caller matrix

日期：2026-08-21
結論：`DECISION_COMPLETE_OPTION_A_CONDITIONAL`；全部engine欄位維持`PENDING_ENGINE`。

## Persistence／composition matrix

| Boundary | Current source | Current fact | Option A contract／owner | Engine evidence |
|---|---|---|---|---|
| base table | `db/schema_parts/137_background_jobs.sql` | `command_identity`為utf8mb4_unicode_ci unique key；receipt/error為nullable JSON | canonical key在DB前限制lowercase ASCII；未知collision fail closed | `PENDING_ENGINE`：`key`／`Key`與191-char boundary |
| durable columns | `db/schema_parts/141_durable_background_job_queue.sql` | type/version/payload/submitted_by/correlation均可保存，legacy允許NULL | canonical reader要求全部exact non-null；legacy不得進canonical path | `PENDING_ENGINE`：JSON `1`／`1.0`、Unicode、null、array/object order |
| command model | `shared_kernel/durable_job_queue.py` | command envelope含type/version/payload/actor/correlation | Core建立closed validation及canonical serialization | production pending Core |
| enqueue/read/claim | `infrastructure/mysql/background_job_repository.py` | duplicate只依identity；reader有fallback；methods直接commit/rollback | Core建立no-hidden-commit port、exact equality與strict reader | production＋engine pending Core |
| complete/fail | `infrastructure/mysql/background_job_repository.py` | receipt/error以raw JSON寫入並自行commit | closed discriminator＋schema version；application為唯一commit owner | production pending Core |
| worker | `subsystems/jobs/durable_job_worker.py` | handler registry涵蓋八command；generic exception可進raw message | typed terminal/retry union，不洩漏raw exception | production pending Core |
| runtime composition | `api/dependencies/private_operations.py::run_durable_job_cycle` | connection／worker／heartbeat transaction邊界需閉合 | Caller Bridge/application composition唯一UoW；close一次 | production pending Core／Bridge |
| public view | `api/schemas/jobs.py`、`api/routes/jobs.py` | legacy view仍有raw `dict[str, Any]` receipt/error | caller adoption後才建立masked bounded union | production pending Public Outcome |

## Six owners／eight command types

| Owner | Command type(s) | Current enqueue／replay behavior | Adoption owner | Status |
|---|---|---|---|---|
| Assignment Plan | `assignment_plan_apply` | route catches `JobIdempotencyConflict` and returns old job without equality proof | Assignment Plan caller successor | `PENDING_ENGINE_AND_ADOPTION` |
| Finance Import | `finance_import_historical_reprocess_apply`; `finance_import_batch_apply`; `finance_import_correction_apply` | route contains sync test-double fallback and treats duplicate as replay | approved FI-H sole writer | `BLOCKED_PREREQUISITES` |
| Government Subsidy | `government_subsidy_apply` with closed action payload | shared enqueue helper returns old job on conflict | Government Subsidy caller successor | `PENDING_CORE_BRIDGE` |
| Payroll Rebuild | `payroll_rebuild_apply` | route returns old job on conflict | Payroll caller successor | `PENDING_CORE_BRIDGE` |
| Staff Payout | `staff_payout_apply` | shared response helper returns old job on conflict | 4B-SP-H sole writer | `PENDING_CORE_BRIDGE` |
| Orders Auto Completion | `orders_auto_completion_apply` | subsystem dispatcher owns enqueue; equality adoption not closed | Orders Auto caller successor | `PENDING_CORE_BRIDGE` |

## Scenario disposition

- `JOB-DURABLE-001`：`SUPPLEMENT`；需加入exact equality、closed terminal outcome與caller-specific replay oracle。
- `JOB-QUEUE-LIFECYCLE-002`：`SUPPLEMENT`；需加入no-hidden-commit、claim/retry/exhaustion/crash-resume oracle。
- Fixture／expected／receipt由Phase4 Scenario Lineage owner建立；本decision不自造測試資料或runtime receipt。

若任何disposable MySQL check證明typed equality無法由現有欄位穩定重建，結果固定
`BLOCKED_DB_SUCCESSOR_REQUIRED`，不得修改已發布137／141 bytes，必須另立additive release successor。
