---
doc_type: receipt
date: 2026-08-07
---

# Finance Import Legacy Import-Path Repair Receipt

日期：2026-08-07

## 背景

「架構重整」分支合併後（HEAD `86d1a88`），多個檔案的 import 仍指向重構前
（commit `2ad0f36` 之前）的 `services/*` 模組路徑，但對應模組實際上已搬遷至
`domains/*`、`subsystems/*` 或 `infrastructure/mysql/mysql_adapter.py`，導致
FastAPI 啟動時、以及部分 legacy service 模組被 import 時直接拋出
`ModuleNotFoundError`。本收據記錄本次逐項核對與修正的範圍、依據與現況。

本次工作屬於**執行修正**，不涉及任何規格變更；`document/架構重整` 既有規格文件
內容未被修改，僅新增本檔案。

## 修正範圍與依據

以下每一項在修正前，均先以 `grep -rn "^def <function_name>"` 確認目標函式
確實存在於建議路徑，才進行修正，不採信未經驗證的路徑猜測。

| 檔案 | 修正前 | 修正後 | 驗證方式 |
|---|---|---|---|
| `scripts/migrate_order_lifecycle_control_facts.py` | `from services.db_service import DB_CONFIG, get_connection` | `from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection` | 確認 `infrastructure/mysql/mysql_adapter.py` 存在 `get_connection`、`DB_CONFIG` |
| `services/finance_import_application.py` | `from services.db_service import get_connection` | `from infrastructure.mysql.mysql_adapter import get_connection` | 同上 |
| `services/finance_import_application.py` | `from services.finance_identity_maps import load_finance_identity_maps` | `from subsystems.finance_import.identity_maps import load_finance_identity_maps` | 確認 `subsystems/finance_import/identity_maps.py` 存在該函式 |
| `services/finance_import_application.py` | `from services.finance_import_staging import stage_finance_rows` | `from subsystems.finance_import.staging import stage_finance_rows` | 確認 `subsystems/finance_import/staging.py` 存在該函式 |
| `services/finance_import_application.py` | `from services.order_amount_calculator import calculate_order_amounts` | `from domains.client_finance.order_amount_calculation import calculate_order_amounts` | 確認該模組存在該函式 |
| `services/finance_import_dispatch.py` | `from services.client_receipt_reconciliation import reconcile_client_receipt` | `from subsystems.client_finance.receipt_reconciliation import reconcile_client_receipt` | 確認該模組存在該函式 |
| `services/finance_import_dispatch.py` | `from services.finance_alert_wiring import maybe_alert_pending` | `from subsystems.finance_import.reconciliation_dispatch import maybe_alert_pending` | 確認該模組存在同名函式 |
| `services/finance_import_dispatch.py` | `from services.government_subsidy_reconciliation import reconcile_government_subsidy` | `from subsystems.government_subsidy.receipt_reconciliation import reconcile_government_subsidy` | 確認該模組存在該函式 |
| `services/finance_import_dispatch.py` | `from services.staff_actual_transfers import reconcile_staff_actual_transfer` | `from subsystems.staff_payables.actual_transfer_reconciliation import reconcile_staff_actual_transfer` | 確認該模組存在該函式 |
| `services/finance_import_reprocessing.py` | `from services.db_service import get_connection` | `from infrastructure.mysql.mysql_adapter import get_connection` | 同上 |
| `services/finance_import_reprocessing.py` | `from services.finance_identity_maps import load_finance_identity_maps` | `from subsystems.finance_import.identity_maps import load_finance_identity_maps` | 同上 |
| `tests/test_finance_import_recovery_subsystem.py` | `from services.db_service import DB_CONFIG` | `from infrastructure.mysql.mysql_adapter import DB_CONFIG` | 同上 |
| `subsystems/finance_import/staging.py` | `from services.finance_transaction_classifier import classify_finance_transaction`<br>`from services.finance_transaction_fingerprint import build_dedup_fingerprint` | `from domains.finance_import.transaction_classifier import classify_finance_transaction`<br>`from domains.finance_import.transaction_fingerprint import build_dedup_fingerprint` | 確認兩個函式都已搬至 `domains/finance_import/` |
| `services/finance_import_reprocessing.py` | `from services.finance_transaction_classifier import classify_finance_transaction` | `from domains.finance_import.transaction_classifier import classify_finance_transaction` | 同上 |
| `tests/test_finance_import_dry_run.py` | 同上兩項 classifier／fingerprint import | 同上 | 同上 |
| `tests/test_finance_import_recovery_subsystem.py` | `from services.finance_transaction_classifier import classify_finance_transaction` | `from domains.finance_import.transaction_classifier import classify_finance_transaction` | 同上 |
| `tests/test_finance_transaction_classifier.py` | `from services.finance_transaction_classifier import classify_finance_transaction` | `from domains.finance_import.transaction_classifier import classify_finance_transaction` | 同上 |
| `domains/finance_import/transaction_classifier.py` | `from services.finance_cancellation_code import resolve_finance_cancellation_code` | `from domains.finance_import.cancellation_code import resolve_finance_cancellation_code` | 確認 `domains/finance_import/cancellation_code.py` 存在該函式 |
| `tests/test_finance_cancellation_code.py` | 同上 | 同上 | 同上 |

另修正 `db/schema.sql` 的執行順序問題：`v_order_details` 檢視表原本直接參照
`orders.lifecycle_version`，但該欄位由 `db/schema_parts/106_order_lifecycle_control_facts.sql`
才新增，而 `scripts/init_db.py` 會先跑完整個 `schema.sql` 才載入
`schema_parts/`，導致全新資料庫初始化時視圖建立失敗、連帶中斷後續資料表建立。
已將該視圖定義搬至新檔 `db/schema_parts/999_v_order_details_view.sql`，確保在
所有附加遷移之後才執行。

另修正 `main_02_orders.py`、`main_03_calendar.py` 原始檔為 UTF-16LE 編碼造成
flake8 `E999`（誤判為 null bytes）：轉為 UTF-8，內容未變更。
`ui/pages/anomalies/beclass_import_review_panel.py` 補上缺漏的 `Mapping` import
（flake8 `F821`）。

## 已知未修正、刻意保留的缺口：`client_subsidy_return` dispatch

`services/finance_import_dispatch.py` 原本 import
`services.client_subsidy_return_transactions.record_client_subsidy_return`，
但該模組已於重構 commit `2ad0f36` 隨 `subsidy_return` 交易模型一併移除，取而代之
的是新的 `subsidy_advance` 結算模型（見
[`25_Client_Refund_Completion_Decision_Package.md`](../work_packages/25_Client_Refund_Completion_Decision_Package.md) 第 22 行附近：
「`subsystems/client_finance/subsidy_return_reconciliation.py` 已於零 caller
的完整 runtime/maintenance caller 掃描後退役，其三個 projection writer 已不存在，
且不得以相容路徑重新引入」）。

**未依樣重建 `record_client_subsidy_return`**，因為新舊模型語意不同，重建等同於
未經授權替規格做決定。改採 fail-closed：`dispatch_finance_import_row` 在
`classification_type == "client_subsidy_return"` 分支直接 `raise
NotImplementedError`，並在程式碼註解中標明原因與本文件出處。此舉解除了原本
「整個 `finance_import_dispatch` 模組 import 失敗、連帶拖垮
`finance_import_application.py`／`finance_import_reprocessing.py` 全部分類」的
阻斷狀態，同時不假裝這條分類已有正式實作。

**待決事項**：`client_subsidy_return` 分類的行在新 `subsidy_advance` 模型下應該
如何 dispatch，需要熟悉該模型的人另立正式規格／Decision Package 後才能實作，
不在本次修正範圍內。

## 驗證

- `PYTHONPATH=. .venv\Scripts\python.exe -c "from api.main import app"` 成功匯入。
- `PYTHONPATH=. .venv\Scripts\python.exe -c "import services.finance_import_dispatch"`、
  `import services.finance_import_reprocessing`、`import services.finance_import_application`
  均成功匯入。
- `uvx flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=.venv`
  回報 0 個錯誤（對應 GitHub Actions「Lint with flake8」的 build-blocking 檢查）。
- `scripts/init_db.py` 對全新資料庫完整執行 40 個 schema 語句與全部
  `schema_parts` 成功，`government_subsidy_outbox`、`v_order_details` 均確認建立。

## 未涵蓋範圍

- `api/routes/finance_alerts.py`、`api/routes/system_alerts.py` 的
  `services.db_service`、`services.finance_alert_workflow` import 問題**尚未修正**，
  留待下一輪處理（連同 `ui/pages/06_finance_alerts.py` 與
  `ui/pages/anomalies/registry_panel.py` 的導覽掛載問題一併評估）。
- `services/finance_import_states.py`、`finance_import_dispatch.py`、
  `finance_import_application.py`、`finance_import_reprocessing.py`、
  `finance_import_review_alerts.py` 五個 legacy service 本身**未退役**，依
  [`09_Finance_Import_Domain.md`](../../01_規格基線/09_Finance_Import_Domain.md) 第 573～596 行
  仍在「現況吸收」階段，尚未開始退役工作前置條件未滿足，本次僅修正其 import
  路徑使其可正常運作，不構成退役完成。

## Rollback

本次異動皆為 import 路徑字串替換、一個檔案的視圖定義搬移、兩個檔案的編碼轉換、
一處 import 補漏，以及一處以 `raise NotImplementedError` 取代死 import。如需回退，
可個別 `git revert` 對應 commit；回退後上列驗證項目會重新失敗，屬預期行為。
