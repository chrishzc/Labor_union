# Module: local-database-fresh-reset

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
提供 localhost development 的 explicit fresh-schema reset：operator `union_db`
必須先產生 canonical plan 並確認 `RESET`；自動驗收只使用明確 `lu_test_*`
target。此 Module 不屬於 preserved-data additive upgrade，也不載入 business
fixture。

## Implementation
- primary:
  - `scripts/reset_fake_database.py`
  - `scripts/bootstrap_disposable_mysql_schema.py`
- entrypoints:
  - `scripts/launchers/reset_DB.bat`
- config:
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/local-database-fresh-reset/`

## Provenance
- Fresh bootstrap 與 preserve-data upgrade 是分離流程 — `architecture_declared` —
  `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- Flat tests prove release／schema／migration and operator-entry behavior —
  `architecture_declared` — `.arch-map/tests/index.md`

## Change triggers
- Reconcile when fresh reset target policy、confirmation、plan／receipt、canonical
  assembly、entrypoint 或 fresh-engine verification routing changes.
