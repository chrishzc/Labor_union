---
doc_type: work-package
declared_status: approved
date: 2026-08-14
approved_at: 2026-08-14
owner: Database Architecture / Release Engineering
priority: P1
depends_on: WP92
---

# 93 Schema Assembly 與 Migration Archive 退役 Work Package

## Business scenario

開發者建立 fresh disposable database 時，現行 loader 以 glob 載入全部 `db/schema_parts/*.sql`；但 preserve-data
release catalog 只選部分 artifact。隨著 schema part 增加，已被後續變更取代的歷史 artifact 仍會被 fresh bootstrap
重播，造成 assembly 邊界、版本責任與驗證成本不清楚。

## Scope

1. 為每個 schema part 建立唯一 catalog classification：`active-bootstrap`、`migration-only`、`retired`。
2. 建立明確的 fresh-bootstrap assembly manifest，取代 glob 全載入。
3. 保留 preserve-data release chain、release descriptor、checksum 與已發布 migration bytes；不得改寫、刪除或改號。
4. 先處理已明確無現行 owned object 的 retirement artifact，例如 `153_retire_empty_legacy_field_inventory.sql`：保留為
   migration-only evidence，不再列入 future fresh bootstrap。
5. 每一個移出 fresh assembly 的 artifact 必須有 successor／終態 schema evidence、依賴盤點與回復條件。
6. 擴充 preserve-data release descriptor，使 `CREATE OR REPLACE VIEW` 有可機械驗證的 owned-view contract；不得以
   無意義的 table ALTER 作為 view release 的完成標記。

## Out of scope

- 刪除既有 schema part、release manifest、migration receipt 或正式資料。
- 修改 HCM／Case Import 業務規則、WP88 warning 行為或正式資料庫。
- 將現有 migration-only artifact 自動視為可刪除。

## Required acceptance

1. fresh bootstrap、preserve-data candidate upgrade 與 release catalog 各有獨立、可驗證的 manifest。
2. 每個 retirement candidate 有 source object、successor、資料效果、replay、rollback 與 unresolved policy。
3. disposable fresh DB 與上一支援版 preserve-data candidate 均驗證 PASS。
4. `init_db.py`、disposable bootstrap、validation release 與 migration runner 不再對同一 artifact 有未宣告的不同選取規則。
5. 一個含 view 更新的 release 在 candidate 上可區分 `absent`、`exact`、`partial`、`drift`，並在 dump → restore 後
   驗證 view definition 的語意等價性。

## Current evidence

- `scripts/init_db.py` 與 disposable bootstrap 目前以 glob 讀取全部 part。
- `scripts/migrate_preserved_database_additive_schema.py` 使用 explicit `DEFAULT_RELEASE_MANIFESTS`。
- `153_retire_empty_legacy_field_inventory.sql` 已是 retirement action，但仍被 fresh bootstrap 重播。
- WP88 的 `待補件` formal case 的帳務資格由 Orders 狀態機與未建立的帳務 root facts 共同控制；`v_order_details`
  的預估欄位不是寫入授權，因此不是 WP88 completion 的 schema 依賴。若日後需要調整其顯示，仍須先由本 WP 提供
  view owner descriptor，才能以可追溯 release 更新既有資料庫。

本工作包尚未經人工核准，不授權 implementation、schema mutation、archive 搬移或刪除。

## 2026-08-14 授權補充

人工授權先建立 WP80 的明確 `pre-190 → 190_historical_order_adoption.sql` release assembly chain，
以完成 isolated preserve-data candidate 驗證。不得改寫既有發布 SQL、既有 manifest bytes、正式資料或
擴張為其他 schema part 的 retirement；其他 WP89 scope 仍須逐項驗收後實作。
