---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Global Migration / Developer Experience
priority: P0
---

# 74 開發者本機資料庫更新與重建 Work Package

## 1. 人工裁決與 business scenario

2026-08-13 人工確認修復不同開發者自 `main` 取得程式後，因本機 schema 未同步而造成的 API 500、
runtime monitor 與 outbox worker 缺表問題，並要求提供可更新或重建開發者自有資料庫的腳本。

操作者是開發者；目標只允許 localhost 的開發資料庫。服務啟動成功不代表 schema ready，更新或
重建完成前必須驗證 `government_subsidy_outbox`、`runtime_service_heartbeats`、
`caregiver_matching_plans` 與 `v_order_details` 等必要物件。

## 2. 核准架構

- Global：擁有 migration manifest、schema part 順序、backup／receipt、candidate 驗證與 `.env` switch。
- Domain：不變更任何業務規則或根事實；資料只由既有 migration verifier 證明保留。
- Subsystem：source full dump → restore new candidate → additive schema／backfill → verify → candidate dump → same-name source rebuild → final verify。只有 verified candidate 與 rollback dump 都存在時，才可刪除舊 `union_db`。
- Module／Entry point：`scripts/update_local_database.py`、`scripts/launchers/update_local_database.bat`、
  既有 `scripts/reset_fake_database.py` 與 `scripts/launchers/reset_DB.bat`。

Migration 不得直接在 source 執行 DDL。保留資料的同名重建是破壞性 cutover，必須先通過零 DB
寫入 preflight，再要求 `UPDATE` 與 `--confirm-database union_db`。模板 reset 是另一條 canonical
workflow：預檢固定 fixture 後要求 `RESET`，捨棄目前資料並載入模板。兩者都拒絕 remote／production
target，不得互為相容別名。

已知 `main` reset 可能在 part 181 的 `matching_schedule_snapshots` 外鍵失敗後留下前置表；
`181_matching_service_date_confirmation.sql` 全部採 `CREATE TABLE IF NOT EXISTS`，因此本地 workflow
明確允許只對 part 181 從頭重播。其他 partial 與所有 drift 維持 blocking。

## 3. Scope／write set

- 上述四個 developer-local entry points，以及 launcher 統一目錄中的固定路徑。
- `scripts/migrate_preserved_database_additive_schema.py` 的 candidate verification status 修正。
- 對應 focused tests、README、entrypoint inventory、本 Work Package 與 evidence receipt。
- 不修改 Domain、API、UI、production database、正式主機或 deployment configuration。

## 4. Acceptance

2026-08-13 人工最終裁決把真實 MySQL 驗收拆成兩個隔離方向，不直接修改 `union_db`：

1. 空的 `lu_test_wp74_schema_*` 從 part 187 基線直接套用 WP72，驗證新增欄位與資料表，不複製資料。
2. 目前設定的 `lu_test_*` DB 維持唯讀，full dump 還原至 `lu_test_wp74_data_*` 後執行 WP72
   migration／verify，驗證既有 row count、primary-key fingerprint 與欄位級投影保留。
3. 除明確 allowlist 的 part 181 partial 外，其他 partial／drift、remote host、production environment、非 `union_db` destructive target 與錯誤確認字串皆 fail closed。
4. focused pytest、strict UTF-8 與 `git diff --check` 通過。
5. 兩個真實 MySQL 方向都成功且自動清除 disposable DB；不得宣稱已替任何開發者修改其
   `union_db`，operator 仍須自行執行 launcher 並保留 receipt。

## 5. Out of scope／rollback

- 不自動更新 production、shared staging 或遠端資料庫。
- source replacement 失敗時以第一份 full dump 自動重建並驗證 rollback；candidate 與 receipts 保留供人工診斷。
- 不替開發者猜測或合併 drift schema；遇到 drift 應保留 receipt，改採人工判讀或固定 fixture 重建。
- 本任務不啟動服務、不修改任何現有來源資料庫；只允許建立並在成功後刪除 `lu_test_wp74_*`
  disposable DB。

## 6. Evidence

- [`2026-08-13_developer_local_database_maintenance_receipt.md`](../receipts/2026-08-13_developer_local_database_maintenance_receipt.md)
