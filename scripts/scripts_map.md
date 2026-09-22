# Scripts 入口與驗證

本頁區分可直接操作的命令與仍供程式／測試匯入的函式庫。檔名含 `migrate`、`seed` 或 `verify` 不代表它仍是可執行命令，也不代表已在 CI 執行。

## 開發與維運入口

| 入口 | 用途與效果 |
| --- | --- |
| `scripts/launchers/start_local_development.bat`／`scripts/launchers/start_local_development.sh` | 標準本機啟動；組合 FastAPI、React 與背景 worker。選項及 dry run 見 [launchers/README.md](launchers/README.md)。 |
| `scripts/update_local_database.py` | 保留資料的本機更新；預覽與 Apply 分開，沿用既有 release、backup、identity 與 confirmation 條件。 |
| `scripts/reset_fake_database.py` | 明確目標的 fresh reset；可刪除資料，不是保留資料更新。`reset_DB.bat` 委派此入口。 |
| `scripts/migrate_preserved_database_additive_schema.py` | 正式 preserve-data release runner；保留既有安全邊界與選用 rehearsal 模式，不因命令清理放寬資料庫條件。 |
| `scripts/run_durable_job_worker.py`、`scripts/run_incident_worker.py`、`scripts/run_service_monitor.py`、`scripts/run_line_worker.py`、`scripts/run_knowledge_worker.py` | 背景服務入口；通常由啟動器組合，不是資料準備腳本。 |
| `scripts/imports/import_finance_excel.py`、`scripts/imports/rehearse_case_import_workbook.py` | Workbook 格式／資料預覽，不寫入資料庫；可選的 report 參數會寫入本機報告。詳見 [imports/imports_map.md](imports/imports_map.md)。 |

上述是主要操作入口，不是所有工具的完整列舉。其他保留命令仍依各自參數與既有契約運作。

## 已移除命令與保留函式庫

要求隔離 `lu_test_*` 目標的獨立資料準備、情境執行、readback 與管理測試命令已移除；不是只拿掉資料庫名稱檢查。沒有保留轉接命令或新的拒絕執行 stub。

下列檔案因仍有程式或測試引用而保留，**只有函式庫介面，沒有 `main()` 或 `__main__` 命令入口**：

- Schema／migration helpers：`scripts/init_db.py`、`scripts/migrate_remove_other_addition.py`、`scripts/bootstrap_disposable_mysql_schema.py`、`scripts/backfill_canonical_accounting_projections.py`、`scripts/collect_local_additive_engine_evidence.py`、`scripts/migrate_assignment_schedule_integrity.py`、`scripts/migrate_legacy_ui_dataset.py`、`scripts/plan_legacy_ui_dataset_integration.py`。
- Dataset／scenario helpers：`scripts/run_case_import_invalid_scenario.py`、`scripts/seed_payment_schedule_normal_case.py`、`scripts/seed_ui_validation_dataset.py`、`scripts/seed_validation_beclass_review.py`、`scripts/seed_validation_dataset.py`、`scripts/seed_validation_finance_manual_review.py`、`scripts/verify_case_import_invalid_scenario.py`、`scripts/verify_finance_manual_review_scenario.py`、`scripts/verify_integrated_ui_validation_dataset.py`、`scripts/verify_legacy_ui_preservation.py`。

保留函式的目標限制、交易行為與呼叫契約未放寬。測試可繼續匯入它們；使用者不應以 `python 檔名.py` 當成維運命令。版本化 migration artifacts、歷史 receipts 與業務 API 不在此次刪除範圍。

## CI 實際驗證範圍

`.github/workflows/python-app.yml` 在 main push 與 PR 執行 Python 語法檢查，以及下列不需要資料庫、不安裝專案依賴的檢查：

```bash
python -m unittest discover -s tests -p test_migrate_admin_capability_grants_schema.py
python -m scripts.verify_validation_schema_manifest
python -m scripts.build_validation_schema_release --check
```

第一項檢查退役檔案、函式庫入口、失效 imports、文件中的腳本路徑，以及已失去 runner 的情境狀態。後兩項實際比對 schema manifest 與 SQL release 內容，不連線 MySQL，也不重建 release。

已安裝專案測試依賴的環境可執行直接相關的功能回歸：

```bash
python -m pytest -q tests/test_finance_import_cli_test_adapter.py tests/test_verify_validation_schema_manifest.py
```

CI 成功不代表完整 pytest、MySQL integration、瀏覽器驗收或外部 LINE 效果已通過。失去獨立執行命令的驗證情境標示為 `blocked`；歷史回執只證明當時記錄的 revision。
