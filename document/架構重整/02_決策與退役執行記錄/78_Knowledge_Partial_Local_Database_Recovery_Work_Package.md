---
doc_type: work-package
declared_status: in-progress
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
- 148 只允許已存在 table 的 column/index/FK/check exact，缺少整張 table 才可補建。
- 163 依 `source_identity` column/unique index 判斷 ALTER boundary，不重複執行已完成 ALTER。
- source 不執行 DDL；source backup 必須早於 candidate restore 與任何 migration。
- 只允許 163 已發布的 deterministic `source_identity`/version backfill；其他根事實必須保留。
- 不操作任何現有開發者 DB，不修改 schema SQL 或 release identity。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | 無新 schema；只恢復已發布 148/163 的缺少物件 | candidate 內 replay；source backup 可 rollback |
| system-seed | 無 | 不適用 |
| business-row-backfill | 163 已發布 deterministic backfill | receipt 記錄；只在 candidate |
| destructive | 最後已驗證的同名替換 | source dump 自動 rollback |

## 驗收

1. 直接 script 與 module/BAT 入口都不再發生 `No module named 'scripts'`。
2. 148/163 可證明 partial 能 source dump → candidate restore → apply → exact。
3. 已完成 ALTER 不重跑；缺 index 只補 index；不可能邊界與缺欄位 table 仍阻擋。
4. 資料列數、PK 與非 163 backfill 根事實保留。
5. 目標開發者 DB 實際驗收後才可標記 completed。
