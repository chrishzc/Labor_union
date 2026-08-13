# 2026-08-13 開發者本機資料庫維護 focused receipt

- Work Package：`74_Developer_Local_Database_Update_and_Rebuild_Work_Package.md`
- 驗證環境：Windows、專案 `.venv`；未連線或修改任何 MySQL database。
- focused command：`.venv\Scripts\python.exe -m pytest tests/test_local_database_maintenance.py tests/test_reset_fake_database_entrypoint.py tests/test_update_local_database_entrypoint.py tests/test_migrate_preserved_database_additive_schema_cli.py -q -W error --basetemp .pytest_tmp/local-db-maintenance`
- 最終合併 focused／preserve-data regression：`80 passed, 1 skipped in 2.87s`，包含 part 181 partial resume、source data／schema stale guard 與 replacement rollback；skip 為既有環境條件測試。
- 已驗證：local／production／canonical destructive target guard、part 181 partial-only resume allowlist、source backup→candidate restore→versioned schema→verify→same-name replacement 編排、source stale guard、互動式確認與 backfilled candidate verification gate。
- 尚未驗證：真實 MySQL dump／restore／DDL、同名 replacement／rollback 與 API／worker smoke；因此 Work Package 維持 `in-progress`。
