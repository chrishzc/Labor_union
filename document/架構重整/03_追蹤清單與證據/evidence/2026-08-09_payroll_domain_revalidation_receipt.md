---
scope: 03_Payroll_Domain
status: verified
verified_at: 2026-08-09
---

# Payroll Domain 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/03_Payroll_Domain.md`
- 決策／退役記錄：
  - `37_Durable_Job_Payroll_Rebuild_Work_Package.md`
  - `39_Durable_Job_Staff_Payout_Work_Package.md`
  - `47_Scheduling_Payroll_Legacy_Writer_Exit_Inventory_Receipt.md`
- 既有 G13 競爭證據：`evidence/2026-08-08_g13_leave_cancellation_mysql_receipt.md`

## 實作檢查結果

- Payroll Rebuild、Payroll Adjustment 與 Staff Payout 都以 typed Preview/Apply、
  aggregate version、preview fingerprint、idempotency receipt 與 outer UoW 執行。
- `PayrollRebuildWorkflow` 在鎖定 fresh facts 後只重建未核銷 obligation；已有付款
  歷史時改以 immutable delta obligation 處理，不覆寫 frozen obligation。
- `payroll_rebuild_apply` 與 `staff_payout_apply` 均由 versioned durable command
  envelope 交給獨立 worker，以新連線重建原 request；同 key 重送不會重複寫入。
- 價格、正式服務日、special pay、樓層費分配及 adjustment 都在 Payroll 的純計算
  candidate 中形成整數 NTD 結果；UI 不提供 hourly-rate 或 actual-hours 寫入入口。
- production `staff_obligations`、rate snapshot、adjustment、payroll outbox writer
  位於 Payroll MySQL persistence boundary；搜尋未發現 runtime 對 legacy
  `staff_payments` 的直接寫入，僅 fixture／歷史資料工具保留其 seed 用途。

## 驗證結果

```text
.venv\\Scripts\\python.exe -m pytest -q [Payroll rebuild, adjustment,
terms impact, due date, staff payout and reconciliation tests]
67 passed in 0.90s

.venv\\Scripts\\python.exe -m pytest -q \
  tests/test_payroll_rebuild_durable_mysql_e2e.py \
  tests/test_staff_payout_durable_mysql_e2e.py
4 passed in 35.74s
```

隔離 E2E 使用 temporary `mysql:8.4` 容器、localhost `127.0.0.1:33306` 與
`lu_test_payroll_e2e`。容器已停止且由 `--rm` 自動移除，沒有使用既有 MySQL 容器。

此證據涵蓋 Payroll Rebuild 的同 key durable replay／expired-lease recovery，以及
Staff Payout 的 payout、return、reversal 三種 canonical bank-fact 路徑。因此 39 號
決策原先列為待補的 isolated MySQL crash/replay proof 已在目前 worktree 補齊。

## Current worktree revalidation

```text
tests/test_payroll_rebuild_workflow.py
tests/test_payroll_rebuild_durable_job.py
tests/test_payroll_adjustment_workflow.py
tests/test_staff_payment_due_date.py
tests/test_assignment_payroll_reconciliation_service.py
53 passed, 1 skipped

tests/test_staff_payout_durable_job.py
tests/test_staff_payout_reconciliation_workflow.py
tests/test_staff_payout_funding.py
tests/test_durable_job_worker.py
16 passed, 3 skipped (the three configuration-gated MySQL nodes)
```

Production-source scan found no runtime DML against legacy `staff_payments`.
The sole match is `scripts/generate_fake_data.py`, a test-data seed utility;
canonical Payroll writes remain limited to `staff_obligations` and immutable
`staff_obligation_events` at the Payroll persistence boundary.
