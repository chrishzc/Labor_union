---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Global Migration / Knowledge Retrieval
priority: P0
---

# 84 Legacy Knowledge Empty Schema Recovery Work Package

## 人工核准與場景

2026-08-13 使用者授權建立 WP84；2026-08-14 另授權保留 updater、修復所有阻塞並完成本機
同名 DB 更新。部分開發者資料庫仍保留 commit `6f0e4f6b` 的 legacy
Knowledge schema；現行 148 的 `CREATE TABLE IF NOT EXISTS` 不會替換同名舊表，163 隨後讀取
不存在的 canonical 欄位而失敗。

## 範圍與不變量

- 只接受可機械證明的完整 historical metadata fingerprint；hybrid、缺欄、型別或 constraint drift 阻擋。
- 除 canonical-exact 的 `knowledge_answer_requests`／`knowledge_jobs` 可保留外，其餘七張
  Knowledge owned tables 必須全部零筆，且不可有 bounded context 外部 inbound FK。
- source 維持唯讀並先完成 dump；只在 candidate 刪除七張空 legacy tables，再重播 canonical
  148／163；兩張 queue tables 的 count、PK hash、checksum 前後必須完全一致。
- 不修改 canonical schema SQL、release identity、manifest hash、system seed 或 business rows。
- 任一可重建 Knowledge table 非空，或兩張保留表 metadata 非 canonical-exact，固定 fail closed；
  `source_trust_tier` 與 actor provenance 不在本案推論。
- interrupted candidate 可保留診斷；重試使用 fresh candidate，source dump 是 rollback evidence。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | candidate-only 空 legacy Knowledge roots 重建為既有 148／163；既有 contract identity migration 於 canonical view 前執行 | canonical exact skip；fresh candidate retry |
| system-seed | 無 | 不適用 |
| business-row-backfill | 保留 requests/jobs；既有 lifecycle migration 只寫其宣告的 control events/state | migration verify 必須 exit 0 且 unresolved=0 |
| destructive | 只刪 candidate 中已證明為空的七張 legacy tables；release 153 只退役零筆 legacy table | source 不變；source dump rollback |

## 驗收

1. read-only plan 只把 exact legacy empty shape 列為 resumable，非空或外部 FK 明確 blocked。
2. disposable MySQL 完成 source → dump → candidate → rebuild → verify；source schema fingerprint 不變。
3. candidate 的 148／163 owned objects exact；七張重建表仍為零筆，兩張 queue tables 完整保留。
4. unknown hybrid、metadata drift 與非空 row 不得進入 mutation。
5. updater 完成 verified candidate、同名 `union_db` replacement 與 `--require-current` 驗證。

## Evidence

- [2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md](../receipts/2026-08-13_wp84_legacy_knowledge_empty_schema_recovery_receipt.md)
