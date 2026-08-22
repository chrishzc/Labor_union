# Durable Job Core open findings

Core 已 local validated；下列責任刻意維持 downstream blocker：

- 6 個 enqueue owner 仍為 `awaiting-caller-adoption`：`api/routes/assignment_plan.py`、`api/routes/finance_import.py`、`api/routes/government_subsidy.py`、`api/routes/payroll_rebuild.py`、`api/routes/staff_payout.py`、`subsystems/orders/auto_completion_job_dispatch.py`。
- 8 種 command type 仍為 `awaiting-caller-adoption`：`assignment_plan_apply`、`finance_import_batch_apply`、`finance_import_correction_apply`、`finance_import_historical_reprocess_apply`、`government_subsidy_apply`、`orders_auto_completion_apply`、`payroll_rebuild_apply`、`staff_payout_apply`。
- Caller Integration Bridge、六 caller adoption 與 Public Outcome 尚未執行；public jobs route/schema/dependency 未改。
- 8 個 Domain handler 仍各開 connection/UoW；crash 位於 Domain 完成與 queue terminal transition 之間時，只能 recovery，Core 不宣稱 atomic、exactly-once 或 system-wide durable contract complete。
- 正式 shared Global spec／索引同步保留給原 main integration writer，未在本 transferred catalog/scenario ownership 中競寫。
