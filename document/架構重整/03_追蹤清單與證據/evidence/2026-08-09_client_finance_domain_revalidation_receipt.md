---
scope: 04_Client_Finance_Domain
status: verified
verified_at: 2026-08-09
---

# Client Finance Domain 規格落地驗證收據

## 追溯依據

- 規格基線：`01_規格基線/04_Client_Finance_Domain.md`
- 決策／退役記錄：
  - `../../04_已完成與上線封存/work_packages/25_Client_Refund_Completion_Decision_Package.md`
  - `42_Client_Finance_Bank_Fact_and_Overdue_Reminder_Decision.md`
  - `../../04_已完成與上線封存/work_packages/45_Client_Finance_Canonical_Overdue_Reminder_Work_Package.md`
- 既有補助墊付證據：
  `evidence/2026-08-04_subsidy_return_and_advance_e2e_receipt.md`

## 本次落地與退役

- 排班的 waiting-deposit lock 釋放與配對狀態改為讀取
  `client_deposit_settlement_projection`；不再以 `client_payments` 或
  `client_payment_transactions` 判定訂金是否為零。projection 缺失時 fail-closed。
- `accounting_source_query` 的付款條款來源改為 `client_payment_terms` root facts，
  不再從 compatibility projection 讀取到期日。
- historical Finance Import 診斷器保留匯入／分類與 rollback-only 報表，但不再呼叫
  legacy receipt transaction writer；正式收款、退款、補助退還與退回只可走 typed
  canonical Finance Import Preview／Apply 與 owning-domain composite。
- 已移除未被 production caller 使用的 legacy receipt reconciliation 實作及其
  direct-side-effect 測試；以 `test_legacy_client_receipt_dispatch_retirement.py`
  固定驗證診斷器只能回傳 pending、不得出現 legacy payment writer。

## 驗證結果

```text
.venv\Scripts\python.exe -m pytest -q [Client Finance、Finance Import
diagnostic retirement、Scheduling deposit boundary focused suite]
116 passed, 1 skipped in 4.17s

.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_client_finance_e2e \
  tests/test_finance_import_disposable_mysql_e2e.py::test_manual_refund_correction_posts_ledger_allocation_and_resolves_anomaly \
  tests/test_finance_import_disposable_mysql_e2e.py::test_real_taishin_subsidy_payout_advances_then_recovers_after_government_allocation \
  tests/test_refund_return_review_disposable_mysql_e2e.py \
  tests/test_g14_deposit_reversal_disposable_mysql_e2e.py
6 passed in 48.79s
```

E2E 使用 fresh `mysql:8.4` 容器，只綁定 `127.0.0.1:33306` 與
`lu_test_client_finance_e2e`。完成後已停止容器（`--rm` 自動移除）並刪除 pytest
workspace 暫存目錄；未使用既有 MySQL 資料庫。

靜態掃描確認上述排班／付款條款／診斷 dispatch 邊界沒有
`client_payments` 或 `client_payment_transactions` 依賴。歷史 reprocess 中僅保留
「已存在舊交易」的 preserve-data 唯讀偵測，未作 legacy 寫入。

## 追加複驗（2026-08-09）

- 無 production caller 的 `subsystems/client_finance/payment_snapshot.py` 曾直接
  `INSERT client_payments`，已連同只驗證該 writer 的測試退役；它不是 canonical
  projection adapter，保留會違反 compatibility projection writer 邊界。
- `api/routes/client_payments.py` 僅保留 compatibility read；其兩個舊 writer endpoint
  均固定回覆 `410`。現行 Finance Import、API、Streamlit 與可執行 scripts 沒有對
  `client_payments`／`client_payment_transactions` 的 DML。
- `scripts/generate_fake_data.py` 的歷史 SQL 雖保留供人工考證，但模組第一個可執行
  敘述即 `SystemExit`，不可 import 或直接執行；`test_generate_fake_data.py` 固定驗證
  此 fail-closed 退役邊界。
- 本次 focused suite：`89 passed, 1 skipped in 5.81s`，包含 obligation／ledger
  reconciliation、refund return/reversal、subsidy advance/recovery、canonical overdue
  reminder、Finance Import dispatch 與 legacy receipt retirement。
