---
doc_type: work-package
declared_status: completed
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

## 結案裁決

2026-08-13 使用者明確指定以「程式修復與遠端發布」作為本 Work Package 的結案條件。
commit `4b15934d` 已推送至 `main`，focused regression 與 disposable MySQL 候選升級均通過。
實際開發者 DB 更新仍未執行，維持獨立 operator acceptance，不構成此程式修復結案的阻塞條件。

## 2026-08-13 本機 candidate 實證補充

本機 preserve-data candidate 顯示 catalog 曾將 stage13 的 179 排在 stage12 的 186 之前；179 需要
`line_identity_revocation_requests`，但該 table 是 186 才建立，MySQL 因 table 不存在 fail closed。
本 Work Package 重新開啟，將 canonical manifest 順序修正為 `186 → 179`，再完成新的 candidate engine evidence。

186 擴充既有事件 enum 時，MySQL `CHECKSUM TABLE` 會因實體表重建而改變，即使既有列完全不變。
驗證器遇此情形改以 source-column projection、列數與 primary key hash 驗證資料不變；projection 不同仍 fail closed。

## 2026-08-13 開發者驗收完成

Docker MySQL 8.0 的 `lu_test_dataset_contract_signing_v4` 已完成 source dump → candidate → schema／backfill
→ preserved-data verify → 同名替換。replacement receipt 與 rollback dump 位於
`scratch/local_database_updates/lu_test_dataset_contract_signing_v4_local_20260813133057/`。
