---
doc_type: work-package
declared_status: blocked
date: 2026-08-13
owner: Global Migration / Developer Experience
priority: P0
---

# 78 Knowledge Partial Local Database Recovery Work Package

## 人工核准與場景

2026-08-13 使用者明確要求修復遠端 `main` 的本機 DB 更新缺口。舊開發資料庫的
`148_knowledge_retrieval.sql` 與 `163_knowledge_runtime.sql` 可能停在已發布 statement boundary，
保留資料升級必須先備份 source，只修復可機械證明的 partial，未知 drift 仍 fail closed。

## 範圍與不變量

- 修正 `python scripts/update_local_database.py` 的 package root；canonical 仍為 `-m` 與 BAT。
- 148 只允許已存在 table 的 column/index/FK/check exact，缺少整張 table 才可補建；已確認的 legacy `knowledge_items.id BIGINT UNSIGNED` 是唯一可保留的 ID shape，所有新建的 Knowledge child FK 欄位必須同型別。
- 163 依 `source_identity` column/unique index 判斷 ALTER boundary，不重複執行已完成 ALTER。
- source 不執行 DDL；source backup 必須早於 candidate restore 與任何 migration。
- 只允許 163 已發布的 deterministic `source_identity`/version backfill；其他根事實必須保留。
- 不操作任何現有開發者 DB，不修改 schema SQL 或 release identity；其他 ID 型別或任何已存在但不相容的 child FK 固定 fail closed。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | 恢復已發布 148/163 的缺少物件；在已確認 legacy unsigned root 上產生同型別 child FK | candidate 內 replay；source backup 可 rollback |
| system-seed | 無 | 不適用 |
| business-row-backfill | 163 已發布 deterministic backfill | receipt 記錄；只在 candidate |
| destructive | 最後已驗證的同名替換 | source dump 自動 rollback |

## 驗收

1. 直接 script 與 module/BAT 入口都不再發生 `No module named 'scripts'`。
2. 148/163 可證明 signed 與已確認 unsigned legacy root 都能 source dump → candidate restore → apply → exact。
3. 已完成 ALTER 不重跑；缺 index 只補 index；不可能邊界與缺欄位 table 仍阻擋。
4. 資料列數、PK 與非 163 backfill 根事實保留。
5. 目標開發者 DB 實際驗收後才可標記 completed。

## 封存撤回（2026-08-14）

`2026-08-13_wp78_wp81_legacy_compatibility_receipt.md` 已確認程式修復與 focused regression，
但 read-only plan、disposable MySQL engine verification 與 developer acceptance 均為 `NOT_RUN`。
依 archive gate，本文件不得視為完成封存；已由 active 索引恢復為 `blocked`，待安全目標 DB
完成 source backup → candidate → apply → verify 後，再補 receipt 與封存裁決。
