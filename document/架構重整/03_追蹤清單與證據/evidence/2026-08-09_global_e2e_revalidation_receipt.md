# Global E2E Revalidation Receipt

- Observed: 2026-08-09
- Decision contract: `02_決策與退役執行記錄/28_Global_E2E_Acceptance_Gap_Package.md`
- Specification: `01_規格基線/00_Global_共同契約.md`
- Isolation: fresh local `mysql:8.4` disposable container bound only to
  `127.0.0.1:33306`; every test target used the `lu_test_global_e2e` schema.
  No `mysql_db` or `union_db` connection was used.

## Test-environment guard

`tests/conftest.py` now maps a complete explicit
`LABOR_UNION_TEST_MYSQL_*` configuration to legacy adapter `DB_*` settings
before collection. A partial test configuration or a conflicting `DB_*` value
is a pytest usage error. This prevents a disposable E2E invocation from
silently reading an application `.env` connection.

## Current-worktree result

| Scenarios | Test evidence | Result |
| --- | --- | --- |
| G01–G04 | `test_order_cancellation_disposable_mysql_e2e.py` | 7 passed |
| G05 | `test_order_auto_completion_disposable_mysql_e2e.py`, `test_order_auto_completion_durable_worker_e2e.py` | 4 passed |
| G06, G13, G15 | refund-lock, leave-cancellation and cache-boundary E2E files | 4 passed |
| G07, G16 | `test_durable_finance_import_batch_e2e.py` | 2 passed |
| G08, G10–G12 | named Finance Import transactional E2E nodes | 10 passed |
| G14 | deposit-reversal, receipt-reconciliation and UI/API E2E files | 5 passed |
| G09, G17 | Finance Import UI/API parity and durable-job UI E2E files | 2 passed |

The earlier `global_e2e_manifest.json` remains a historical 2026-08-08
snapshot. Its source hashes do not bind the current dirty worktree; this
receipt is the current-worktree execution evidence and does not retroactively
alter that historical artifact.
