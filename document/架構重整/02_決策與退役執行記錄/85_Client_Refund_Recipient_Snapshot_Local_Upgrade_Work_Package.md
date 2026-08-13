---
doc_type: work-package
declared_status: completed
date: 2026-08-14
owner: Global Migration / Client Finance
priority: P0
---

# 85 Client Refund Recipient Snapshot Local Upgrade Work Package

## 人工核准與 business scenario

2026-08-14 使用者要求將既有 canonical part 176 納入 versioned release，完成 disposable engine
驗證後直接更新本機 `union_db`，失敗時在本範圍內修復直到 updater 成功。管理 UI 的應付帳款
唯讀查詢目前因 `client_refund_recipient_snapshots` 缺表回 MySQL 1146；fresh bootstrap 已包含該表，
但 preserve-data release chain 漏接，屬 `live-drift`。

## Global → Domain → Subsystem → Module

- Global Migration：新增 successor release identity、artifact hash、owned-object descriptor、candidate
  apply/verify 與同名 replacement receipt。
- Client Finance Domain：退款義務及建立時選定的 immutable recipient-account snapshot 語意不變。
- Staff Payables Subsystem：應付帳款 Query 只讀取既有 root facts，不建立或回填 snapshot。
- MySQL Module／Adapter：沿用 `176_client_refund_recipient_snapshot.sql`；API/UI public contract 不變。

## Scope、write set 與 non-goals

- 新增 successor migration manifest、part 189 bridge 與 descriptor，把既有 part 176 契約接在 WP72 後；
  新編號避免 release artifact ordinal regression，DDL 語意必須與 part 176 相同。
- 帳務 smoke 若揭露同一 release-catalog omission，納入既有 canonical part 169 的完整 part 190
  successor bridge；不得只建 query 所需單表而遺漏 owning Domain 的相依 roots、FK 與 triggers。
- descriptor 必須完整涵蓋六欄、PK、兩個 FK、一個 check 與兩個 immutable triggers。
- source absence、candidate exact、partial/drift 必須機械區分；source 在 replacement 前唯讀。
- 不修改 part 176 SQL、不推論銀行帳戶、不回填既有退款資料、不改 API/UI/Domain 規則。
- 不操作 production/shared staging；本次只授權 `.env` 指向的本機 `union_db`。

## DB change inventory

| 分類 | source artifact／target | 資料效果 | replay／rollback／unresolved |
|---|---|---|---|
| schema-only | part 176 → `client_refund_recipient_snapshots`、2 triggers | absent 時建立；exact 時 skip | statement receipt replay；source dump rollback；partial/drift blocked |
| system-seed | part 190 的 canonical `hccg` payer definition | idempotent definition seed | `ON DUPLICATE KEY UPDATE`；descriptor exact；未知 drift blocked |
| business-row-backfill | 無 | 不建立任何 snapshot row | 不推論；既有退款若缺 snapshot 維持 query anomaly/empty semantics |
| destructive | 無 | 無 DROP／DELETE／rename | 不適用 |

## 驗收

1. runner latest release 與唯讀 plan 明確列出 part 176；WP72 published bytes 不變。
2. descriptor 對 table、columns、PK、FK、check、triggers 判定 absent／exact／partial／drift。
3. disposable fresh bootstrap 與上一支援版 source→dump→candidate→apply→verify 全部通過。
4. source rows、PK 與既有欄位 projection 不變；新 table 為 exact 且零筆。
5. 本機 updater 完成同名 replacement，`--require-current` 為 successor release。
6. 2026-08 應付帳款 application query 不再出現 MySQL 1146。

## Evidence

- `../03_追蹤清單與證據/evidence/2026-08-14_client_refund_snapshot_local_upgrade_receipt.md`
