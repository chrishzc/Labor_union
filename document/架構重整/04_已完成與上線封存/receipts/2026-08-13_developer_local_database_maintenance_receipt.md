# 2026-08-13 開發者本機資料庫維護 focused receipt

- Work Package：`74_Developer_Local_Database_Update_and_Rebuild_Work_Package.md`
- 驗證環境：Windows、專案 `.venv`、本機 `mysql:8.0` Docker；來源 DB 唯讀，未修改 `union_db`。
- focused command：`.venv\Scripts\python.exe -m pytest tests/test_local_database_maintenance.py tests/test_reset_fake_database_entrypoint.py tests/test_update_local_database_entrypoint.py tests/test_migrate_preserved_database_additive_schema_cli.py -q -W error --basetemp .pytest_tmp/local-db-maintenance`
- 最終合併 focused／preserve-data regression：`80 passed, 1 skipped in 2.87s`，包含 part 181 partial resume、source data／schema stale guard 與 replacement rollback；skip 為既有環境條件測試。
- 已驗證：local／production／canonical destructive target guard、part 181 partial-only resume allowlist、source backup→candidate restore→versioned schema→verify→same-name replacement 編排、source stale guard、互動式確認與 backfilled candidate verification gate。
- 2026-08-13 WP72 補驗：預設 versioned release 清單已明確納入 WP68 與 WP72，最後 artifact 為
  `188_matching_preferences_and_staff_availability.sql`；descriptor 會把既有 `orders` 缺少
  `requires_cooking` 判為 partial，不再誤判 exact。WP72 manifest、SQL 與 descriptor hash 已通過
  shared manifest loader。
- WP72 採最小升級設計：part 188 一次建立偏好／不可服務期間資料表、加入 `requires_cooking`，並以
  idempotent SQL 補入預設 definitions 及轉換可明確識別的舊 `staff_time_slots`；未新增通用 backfill
  framework。無法唯一解析或帶 custom detail 的舊值只建立人工 review，不猜測數字。
- 2026-08-13 最終 WP74／WP75 合併 focused regression：`59 passed in 2.46s`（含 `-W error`）。
- 真實 MySQL 第一次執行發現兩個 production-path defect：validation schema ordered digest 未同步，
  以及 PyMySQL `TIME` 值為 `timedelta` 時 preservation verifier 無法 canonicalize。修正後加入穩定
  microseconds 表示與 digest gate。
- 真實 MySQL 最終命令：`.venv\Scripts\python.exe -m pytest
  tests\test_wp74_local_database_upgrade_mysql.py -m integration -q -W error -p no:cacheprovider
  --basetemp .pytest_tmp\wp74-archive-final`；結果 `2 passed in 95.25s`。
- 方向一在空的 `lu_test_wp74_schema_*` 上由 part 187 升級 WP72；方向二把目前
  `lu_test_dataset_contract_signing_v4` full dump 還原到 `lu_test_wp74_data_*`，完成 migration 與
  verify，舊表 row count、primary-key fingerprint 與 source-column projection 均保留。
- 成功後兩個 disposable DB 均自動刪除；先前失敗留下的三個 `lu_test_wp74_*` 亦經固定 regex 與
  information_schema identity 確認後刪除。沒有修改 `union_db` 或來源測試 DB。
- WP74 依 2026-08-13 人工最終兩方向驗收裁決標記 `completed`；同名 replacement 的 destructive
  path 仍由既有 unit／contract test 覆蓋，實際開發者 DB 更新必須由 operator 明確執行。
