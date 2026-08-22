# Durable Job Core candidate change inventory

- Scope：canonical equality、closed terminal outcome、zero-hidden-commit repository port、worker/private UoW composition。
- Production paths：`shared_kernel/durable_job_queue.py`、`subsystems/jobs/contracts.py`、`subsystems/jobs/ports.py`、
  `subsystems/jobs/durable_job_worker.py`、`infrastructure/mysql/background_job_repository.py`、
  `api/dependencies/private_operations.py` 的 durable composition。
- Schema-only／system seed／business-row backfill／destructive production change：全部無。
- Engine setup：測試只在 3 個唯一 `lu_test_*` DB 組裝既有 `137`／`141` queue schema parts，結束後只清除自身 DB。
- Explicit exclusions：caller、public jobs API/schema/dependency、React、LINE/provider、production、既有 DB、ports 8000／5174／8501。

結論：無 schema release，DB gate 總結仍為 `DB_CHANGE_NOT_READY`。
