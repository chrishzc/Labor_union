---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Global Migration / Knowledge Retrieval
priority: P0
---

# 84 Legacy Knowledge Empty Schema Recovery Work Package

## 人工核准與場景

2026-08-13 使用者授權建立 WP84。部分開發者資料庫仍保留 commit `6f0e4f6b` 的 legacy
Knowledge schema；現行 148 的 `CREATE TABLE IF NOT EXISTS` 不會替換同名舊表，163 隨後讀取
不存在的 canonical 欄位而失敗。

## 範圍與不變量

- 只接受可機械證明的完整 historical metadata fingerprint；hybrid、缺欄、型別或 constraint drift 阻擋。
- 九張 Knowledge owned tables 必須全部零筆，且不可有 bounded context 外部 inbound FK。
- source 維持唯讀並先完成 dump；只在 candidate 刪除空 legacy tables，再重播 canonical 148／163。
- 不修改 canonical schema SQL、release identity、manifest hash、system seed 或 business rows。
- 任一 Knowledge table 非空固定 fail closed；`source_trust_tier` 與 actor provenance 不在本案推論。
- interrupted candidate 可保留診斷；重試使用 fresh candidate，source dump 是 rollback evidence。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | candidate-only 空 legacy Knowledge context 重建為既有 148／163 | canonical exact skip；fresh candidate retry |
| system-seed | 無 | 不適用 |
| business-row-backfill | 無 | 非空資料固定 unresolved／blocked |
| destructive | 只刪 candidate 中已證明為空的九張 legacy tables | source 不變；source dump rollback |

## 驗收

1. read-only plan 只把 exact legacy empty shape 列為 resumable，非空或外部 FK 明確 blocked。
2. disposable MySQL 完成 source → dump → candidate → rebuild → verify；source schema fingerprint 不變。
3. candidate 的 148／163 owned objects exact，九張表仍為零筆。
4. unknown hybrid、metadata drift 與非空 row 不得進入 mutation。

## Evidence

- [2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md](../03_追蹤清單與證據/evidence/2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md)
