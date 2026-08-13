---
doc_type: evidence-receipt
declared_status: awaiting-developer-acceptance
date: 2026-08-13
owner: Global Migration / Developer Experience
work_package: ../02_決策與退役執行記錄/78_Knowledge_Partial_Local_Database_Recovery_Work_Package.md
---

# WP78 Knowledge partial 本機資料庫恢復證據

## 結果

- 直接執行 `scripts/update_local_database.py --help` 已不再發生 `No module named 'scripts'`。
- focused regression：`48 passed`。
- disposable MySQL 8.4：`2 passed`；148／163 可證明 partial 完成 source dump → candidate → apply → exact，未知 drift 維持 fail closed。
- 未操作任何既有開發者資料庫；目標開發者實際執行 BAT 仍待驗收。

## 驗證命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_wp78_local_database_partial_recovery.py tests\test_local_database_maintenance.py tests\test_preserved_database_plan_contract.py tests\test_update_local_database_entrypoint.py tests\test_launcher_dry_run.py -q --basetemp .pytest_tmp\wp78-focused-final
```

disposable MySQL 測試由 `tests/test_wp78_partial_recovery_disposable_mysql.py` 執行；測試容器完成後已停止並自動移除。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | WP78 與 2026-08-13 人工修復指示 |
| Change inventory | PASS | WP78 DB change inventory |
| Static release | PASS | 未變更 SQL／release identity；focused catalog tests |
| Descriptor | PASS | 148／163 strict metadata 與 malformed drift negative test |
| Read-only plan | PASS | disposable source 將已知 statement boundary 分類為 partial |
| Engine verification | PASS | disposable MySQL `2 passed` |
| Developer acceptance | NOT_RUN | 尚未操作其他開發者 `.env` 指定 DB |

總結：`DB_CHANGE_NOT_READY`，待開發者執行 `scripts\launchers\update_local_database.bat` 並保存實際 receipt 後結案。
