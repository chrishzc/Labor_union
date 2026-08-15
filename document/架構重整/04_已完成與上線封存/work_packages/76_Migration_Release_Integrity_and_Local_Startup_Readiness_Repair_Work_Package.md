---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Global Migration / Developer Experience / Runtime Supervision
priority: P0
---

# 76 Migration Release Integrity 與本機啟動 Readiness 修復 Work Package

## 1. 人工核准與 business scenario

2026-08-13 人工核准修復目前 `main` 的 preserve-data release catalog 與本機啟動邊界。
其他開發者必須能先以唯讀方式確認本機 DB 是否位於 canonical latest release；schema 未就緒時，
API、runtime monitor、worker、UI 與 File Watcher 都不得被 launcher 啟動。

現況第一個 blocker 是 WP68 release manifest 的 descriptor hash 與 live artifact 不一致；修正後還會
依序遇到 WP68 part 182 hash 不一致。完整 catalog 盤點另發現 part 61 曾由已提交的 legacy retirement
修改，但 base manifest 未同步；現行 runner 又只驗證最後兩個 release 的 artifact hash，因而靜默略過。
`runtime_service_heartbeats` 與 `government_subsidy_outbox` 已存在 canonical release chain，1146 錯誤是
更新器在 preflight 前中止、服務仍連入 stale schema 的下游症狀，不是本包要重建的新表。

## 2. Task Charter 與核准範圍

- Goal：恢復整條 canonical release catalog 的 byte-level integrity，提供可機械判斷的唯讀
  `require-current` gate，並讓本機 launcher 在 stale／drift／catalog corruption 時 fail closed。
- Public contract：`scripts.update_local_database` 預設仍只產生唯讀 plan；launcher 不自動套 migration。
- Invariants：預設 plan 唯讀；Apply 只操作 `.env` 指定且通過 local／non-production guard 的 source DB；
  最終 canonical schema 語意不變；不啟動半套 runtime；catalog 的每個 descriptor 與 schema artifact 都須驗證 exact hash。
- Allowed changes：release metadata correction、catalog loader／CLI error boundary、launcher readiness wiring、
  focused tests、disposable MySQL evidence、文件與 receipt。

## 3. Out of scope

- 不新增或修改 `runtime_service_heartbeats`、`government_subsidy_outbox` 的 DDL。
- 未獲明確 target 授權時，不操作、備份、更新或重建任何既有資料庫。
- 不讓 `start_local_development` 隱式執行 migration。
- 不修 Finance Watcher 的 actor／mode／`.xls` 漂移。
- 不新增 HCM Intake Durable Manifest schema，也不實作 WP73 Web upload。

## 4. DB change inventory

| 分類 | source artifact | target／資料效果 | replay／rollback／unresolved policy |
|---|---|---|---|
| schema-only | 恢復 part 61 published artifact bytes；part 153 維持既有退役 | 最終 DB object 與 row 不變 | 61 可依 published blob 重現；153 replay 使用 `DROP TABLE IF EXISTS`；未知 mismatch fail closed |
| system-seed | 無 | 無 | 不適用 |
| business-row-backfill | 無 | 無 | 不適用 |
| destructive | 僅 disposable DB 測試環境清理 | 不接觸既有 DB | 測試建立與清理由測試 harness 擁有 |

2026-08-13 人工裁決：恢復 part 61 的 published bytes 與原 hash，不改寫歷史 release identity；
既有 part 153 繼續作為唯一退役 artifact。不得因此新增 correction release 或 alternate hash 機制。

## 5. Write set

- 本 Work Package 與同目錄 `README.md`
- `AGENTS.md`
- `db/migration_releases/labor_union_2026_08_02_v1.json`
- `db/migration_releases/labor_union_2026_08_12_wp68_v1.json`
- `db/schema_parts/61_finance_import_reprocessing.sql`（只允許恢復 published bytes）
- `db/cutover_releases/labor_union_validation_schema_v1.json`（只同步 ordered-parts digest）
- `db/releases/labor_union_validation_schema_v1.sql`（由既有 builder 機械重建）
- `scripts/migrate_preserved_database_additive_schema.py`
- `scripts/update_local_database.py`
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/README.md`
- migration catalog、update CLI、launcher readiness 的 focused tests
- `document/架構重整/03_追蹤清單與證據/evidence/` 下本包最小去敏 receipt／索引

若 evidence 顯示必須變更 SQL、descriptor object contract、seed、backfill 或既有資料，立即停止並取得
新的人工核准，不得以本包自動擴張。

## 6. Acceptance

1. 全部 default release descriptor 與 schema artifact hash 都 exact；不再只驗最後兩個 release。
2. 已知壞 descriptor／artifact 的 negative control 以非零狀態與 bounded error fail closed。
3. `.venv\\Scripts\\python.exe -m scripts.update_local_database` 可產生包含 latest release、
   待套／續跑／exact artifact 的唯讀 plan，且不寫 DB。
4. `--require-current` 只在 catalog exact 且 target DB 無 pending／resume／drift 時成功；其他狀態非零。
5. launcher 在 connection ready 後、啟動任何 service 前執行 readiness gate；失敗時沒有 API、UI、
   monitor、worker 或 watcher 被此 launcher 啟動。
6. focused metadata／manifest／plan tests、fresh disposable bootstrap，以及上一支援版含代表性舊資料的
   disposable source → candidate → apply → verify 通過。
7. 預設不連線或修改既有資料庫；developer acceptance 只在全部前置 gate PASS 且另有明確 target
   授權後執行。2026-08-13 使用者明確授權的本機 target 可由 `.env` 的 `DB_DATABASE` 指定。

## 7. Completion gate

只有 DB gate 七項均有 `PASS | BLOCKED | NOT_RUN` 證據、所有必要項為 PASS，且最後相關編輯後
重跑驗證，才可標記 completed。WP76 完成不代表 WP73、Finance Watcher或實際開發者 target DB 已驗收。

part 61 identity、full-chain、唯讀 plan 與 disposable MySQL engine evidence 已通過，證據見
`../03_追蹤清單與證據/evidence/2026-08-13_wp76_migration_release_integrity_readiness_receipt.md`。
2026-08-13 目標主機人工驗收完成：修正 `.env` 的本機 MySQL 認證後，`--require-current`
通過；FastAPI `/docs`、Streamlit `:8501` 與完整 launcher 啟動正常，且未再出現
`runtime_service_heartbeats`／`government_subsidy_outbox` 的 1146 錯誤。七項 DB gate 均 PASS，
本 Work Package 標記 `completed`。此結果不代表 WP73 或 Finance Watcher 已完成。
