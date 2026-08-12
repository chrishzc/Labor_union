---
scope: 01_Orders_Domain
status: verified
verified_at: 2026-08-09
---

# Orders Domain 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/01_Orders_Domain.md`
- 正式 successor：`01_規格基線/01_Orders_Domain.md`、`01_規格基線/02_Assignments_Scheduling_Domain.md`
- 歷史契約：`04_已完成與上線封存/work_packages/33_G05_服務完成時刻與請假代班競爭契約.md`
- 既有 UI/API 收據：`evidence/2026-08-08_g01_g02_orders_ui_api_e2e_receipt.md`

Decision 33 的事實來源維持為 Orders AutoComplete；服務完成與請假代班都以
同一個 lifecycle aggregate version、idempotency key、outbox 與 outer UoW
競爭，沒有以排班投影直接覆蓋訂單狀態。

## 本次修正

`subsystems/line/identity_review_workflow.py` 的客戶 LINE 綁定曾在沒有既有
訂單時插入只含 `case_no/client_id` 的空 `orders` 列。這不是 Case Import 的完整
根事實建立，會繞過 Orders 的服務條款、版本與 bootstrap invariant。

此相容性寫入已移除：LINE 綁定現在只更新客戶身分與建立通知 task；正式訂單根
資料只由 Case Import owner 建立。對應回歸測試明確斷言綁定流程不會 `INSERT INTO orders`。

## 程式碼檢查結果

- Terms、Actual Start、Contract Completion、Cancellation、Reopen、AutoComplete 的
  MySQL writer 都有 optimistic aggregate version 條件，並由各自 Workflow 的
  `MySqlUnitOfWork` 在同一外層交易提交。
- Apply 都以 command fingerprint、Preview fingerprint、idempotency claim/receipt
  處理 replay 與 stale preview。
- Terms／Actual Start／Cancellation 依序重建 Scheduling、Client Finance、Payroll，
  再寫 Orders lifecycle/projection 與 receipt；Contract Completion 在同一交易建立
  三筆 Client Finance obligation impact。
- G14 的訂金撤銷與重新入帳仍透過 Client Finance outbox 回寫 Orders lifecycle
  control，不使用 legacy `client_payments` 寫入。

## 驗證結果

### 模組、Workflow 與 API

```text
.venv\\Scripts\\python.exe -m pytest -q [Orders lifecycle/terms/actual-start/
contract-completion/cancellation/reopen/auto-completion/detail/summary tests]
70 passed in 1.43s

.venv\\Scripts\\python.exe -m pytest -q [上述測試 + LINE binding/provisional registration]
78 passed in 1.64s
```

### 隔離 MySQL 端到端

測試使用暫時的 `mysql:8.4` 容器，只綁定 `127.0.0.1:33306` 與資料庫
`lu_test_orders_e2e`；未使用既有專案 MySQL 容器。

```text
tests/test_order_cancellation_disposable_mysql_e2e.py
7 passed in 59.46s

tests/test_order_auto_completion_disposable_mysql_e2e.py
tests/test_order_auto_completion_durable_worker_e2e.py
4 passed in 34.22s

tests/test_g14_deposit_reversal_disposable_mysql_e2e.py
tests/test_g14_client_receipt_reconciliation_e2e.py
tests/test_g14_deposit_reversal_ui_api_e2e.py
5 passed in 40.42s
```

以上覆蓋 G01–G05、G14 的 Preview/Apply、UI/API、stale/conflict、idempotency、
跨領域 atomic write 與 outbox lifecycle-control 情境。
