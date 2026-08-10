---
scope: 05_Staff_Payables_Export_Domain
status: verified
verified_at: 2026-08-09
---

# Staff Payables／Accounts Payable Export 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/05_Staff_Payables_Export_Domain.md`
- 決策／退役記錄：
  - `39_Durable_Job_Staff_Payout_Work_Package.md`
  - `47_Scheduling_Payroll_Legacy_Writer_Exit_Inventory_Receipt.md`
- 既有 durable payout MySQL E2E 證據：
  `evidence/2026-08-09_payroll_domain_revalidation_receipt.md`

## 本次落地與退役

- Staff Payables 的正式對帳、Payout ledger、Payable Query 與 Accounts Payable
  Export 以 `staff_obligation_events`／`staff_obligations`、canonical outgoing bank facts、
  `staff_payout_events` 與 `staff_payout_obligation_links` 為根事實；export 是純讀取，
  不改付款狀態。
- 已移除未被 production caller 使用的
  `subsystems/staff_payables/actual_transfer_reconciliation.py`。這條舊路徑直接依賴
  `staff_actual_transfers`，不能建立 immutable payout event／obligation links，故不再
  是合法付款 writer。`test_legacy_staff_transfer_reconciliation_retirement.py` 固定驗證
  該 module 及其 production import 均不存在。
- 排班的 actual-hours 調整 guard、case 衝突快照與 Payroll assignment 對帳，已停止讀取
  `staff_monthly_settlements`／`staff_monthly_settlement_details`。歷史月結資料不再讓
  assignment 被鎖定或造成 payout 前置判斷；正式 `staff_obligations` 是唯一現行付款
  projection，而 `staff_payments` 僅供 compatibility read。
- 保留 `subsystems/finance_import/reprocessing.py` 對既有
  `staff_actual_transfers` 的單一 preserve-data 唯讀存在性檢查。它不寫入、不核銷、
  不建立 payout event，僅辨識舊資料，符合歷史資料唯讀保留限制。

## 驗證結果

```text
.venv\Scripts\python.exe -m pytest -q \
  tests/test_assignment_payroll_reconciliation_service.py \
  tests/test_multi_caregiver_schedule_read.py \
  tests/test_legacy_staff_transfer_reconciliation_retirement.py \
  tests/test_staff_payout_reconciliation_workflow.py \
  tests/test_staff_payout_durable_job.py \
  tests/test_staff_payout_funding.py \
  tests/test_accounts_payable_export_api_client.py \
  tests/test_accounts_payable_export_sources.py \
  tests/test_accounts_payable_export_workflow.py
111 passed in 1.65s
```

另外，既有 Payroll 重新驗證已覆蓋 fresh MySQL 上的 durable Staff Payout worker 與
replay／rollback 交易邊界；本次只收斂 legacy read dependency，沒有改變 canonical
payout writer 或 durable job 實作。

靜態掃描結果：production code 中沒有
`staff_monthly_settlements`、`staff_monthly_settlement_details`、
`staff_transfer_allocations` 或 `actual_transfer_reconciliation` 的現況依賴；唯一
`staff_actual_transfers` 命中為上述 preserve-data 唯讀檢查。

## 追加複驗（2026-08-09）

- 重新核對 baseline 與 `CON-SET-002`：`staff_payments` 是 compatibility projection，
  Payroll 的 immutable obligation events 與 `staff_obligations` 才是 Staff Payables
  current projection。Accounts Payable source 已直接讀取 `staff_obligations`。
- 聚焦驗證重跑：`111 passed in 1.96s`；另行驗證 frozen
  `scripts/generate_fake_data.py` 的 fail-closed 邊界：`5 passed in 0.36s`。歷史假資料
  SQL 不可執行，未作為正式 writer。
