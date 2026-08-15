---
doc_type: work-package
declared_status: completed
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

## 2026-08-15 實作與驗收

- 唯一 fresh assembly 為 `db/schema_assembly/labor_union_fresh_schema_v1.json`；它列出所有 part 的
  `active-bootstrap`、`migration-only` 或 `retired` 分類，並以 ordered digest 鎖定 active selection。
- `init_db.py`、disposable bootstrap 與 validation release 都只讀該 catalog；preserve-data runner 驗證 catalog
  完整性，但仍由不可變的 release manifest chain 決定 migration artifact，兩者不互相推導。
- `153_retire_empty_legacy_field_inventory.sql`、189、190 為 migration-only；每筆在 catalog 中有 source object、
  successor、終態、資料效果、replay、rollback 與 unresolved policy。fresh assembly 以 part 199 確保已退役
  finance reclassification roots 不會重建。
- 新增 `labor-union-schema-assembly-2026-08-15-v1` release，將 `999_v_order_details_view.sql` 納入 preserve
  candidate，descriptor 以 definition digest 機械區分 view `absent`、`exact` 與 `drift`。
- `update_local_database.bat --dry-run` 現在先跑 launcher preflight，再跑 canonical read-only migration plan；
  apply 維持 backup → candidate apply/verify → same-name replacement 的既有順序。

## Completion evidence

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope | PASS | 本 Work Package 與 2026-08-14 使用者明確授權 |
| Change inventory | PASS | catalog retirement contracts；僅 schema-only、無 seed／business-row backfill |
| Static release | PASS | `71 passed` focused static suite；catalog、validation manifest 與 release chain digest 全部一致 |
| Descriptor | PASS | `v_order_details` unit contract 覆蓋 `absent/exact/drift`；fresh postcheck 成功 |
| Read-only plan | PASS | `scripts.update_local_database` preview 與 `--require-current` 均回報 `labor-union-schema-assembly-2026-08-15-v1` |
| Engine verification | PASS | fresh bootstrap；WP78/WP84 Docker candidate `7 passed`；missing-view source → candidate 重建後 semantic `exact` |
| Developer acceptance | PASS | `update_local_database.bat --dry-run`、`start_local_development.bat --smoke-test` exit 0；API、Streamlit 與本機 workers health passed |
| UI closeout | PASS | 九個頂層頁面各停留至少五秒；修復訂單摘要對待補件／歷史未知條款的誤判 |

完整去敏命令與結果見
[`2026-08-15_wp93_schema_assembly_and_launcher_receipt.md`](../03_追蹤清單與證據/evidence/2026-08-15_wp93_schema_assembly_and_launcher_receipt.md)。
UI closeout 見
[`2026-08-15_wp93_ui_runtime_sweep_receipt.md`](../03_追蹤清單與證據/evidence/2026-08-15_wp93_ui_runtime_sweep_receipt.md)。

## Out of scope retained

- 未修改已發布的 SQL、既有 release manifest bytes、正式資料或 archive 文件。
- 未處理警示中心、HCM／Case Import 業務規則、或其他 active Work Package 的 completion。

## 2026-08-14 授權補充

人工授權先建立 WP80 的明確 `pre-190 → 190_historical_order_adoption.sql` release assembly chain，
以完成 isolated preserve-data candidate 驗證。不得改寫既有發布 SQL、既有 manifest bytes、正式資料或
擴張為其他 schema part 的 retirement；其他 WP89 scope 仍須逐項驗收後實作。
