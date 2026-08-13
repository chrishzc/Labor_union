---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Global Migration / LINE
priority: P0
---

# 79 LINE Runtime Release Catalog Recovery Work Package

## 人工核准與場景

2026-08-13 使用者要求修復 LINE 身分管理與客服入口同時 HTTP 500。已發布的 runtime manifest
存在，但 preserve-data catalog 漏收 179、184、185、186，舊開發資料庫無法取得對應資料表。

## 範圍與不變量

- 將四個既有 release manifest 依 artifact ordinal 納入 canonical preserve-data chain。
- 不修改既有 SQL、descriptor、release identity 或 business row。
- 已由聚合版 v8 收錄的 LINE stage 2～8 不重複加入。
- source 維持唯讀，仍經 dump → candidate → apply → verify 後才可替換。
- 未知 partial／drift 維持 fail closed；不操作任何現有開發者資料庫。
- 186 只接受已發布的 legacy enum／generated-column 形狀；完整重跑既有四段 SQL，其他 partial 拒絕。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | catalog 恢復既有 179、184、185、186 additive artifacts | candidate replay；source dump rollback |
| system-seed | 無 | 不適用 |
| business-row-backfill | 無新增 | 不適用 |
| destructive | 無新增；沿用驗證後同名替換 | source dump rollback |

## 驗收

1. catalog 機械驗證四個 manifest 均存在且 hash 正確。
2. read-only plan 能列出缺少／exact／blocked 狀態。
3. disposable MySQL 能建立 185 客服與 186 身分管理物件。
4. 開發者更新後，兩個 API 不再因缺表回 HTTP 500。
5. 代表性舊 DB 將 186 列為 resumable；未知欄位型別仍 fail closed。
