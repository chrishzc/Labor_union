# Module: local-database-fresh-reset

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
提供 localhost development 的 explicit fresh-schema reset：operator `union_db`
必須先產生 canonical plan 並確認 `RESET`；自動驗收不再強制 disposable DB 或 `lu_test_*`
前綴，可使用 localhost development 的 `union_db`，但 reset 仍須明確授權與目標確認。此 Module 不屬於 preserved-data additive upgrade，也不載入 business
fixture。
本機完整初始化與 reset 共用 NAS 的 hash-bound compact final schema；只有明確 base_only/max_schema_part
的 predecessor／歷史 fixture 繼續使用原 assembly。保留資料升級不經 compact reset。
Operator reset preserves the existing root account, MFA factor, recovery-code consumption
and required root LINE identity parent through an encrypted durable backup and exact
readback. Sessions and non-root accounts are not preserved; no MFA seed is generated.

## Implementation
- primary:
  - `scripts/retire_client_payment_destination.py` — separately authorized three-table localhost retirement with plan, backup, qualified engine and full other-table preservation; not an additive/reset operation.
  - `scripts/reset_fake_database.py`
  - `scripts/reset_root_authentication.py` — root-only capture, encrypted backup and exact restoration.
  - `scripts/bootstrap_disposable_mysql_schema.py` — library-only；沒有獨立命令入口。
  - `scripts/compact_fresh_schema.py` — 共用 current final schema loader。
  - `scripts/verify_verification_scenarios.py`
- entrypoints:
  - `scripts/launchers/reset_DB.bat`
- config:
  - `db/releases/labor_union_validation_schema_reused_pairing_check_v1.sql` — v59 fresh source，與 243 reused pairing CHECK successor／compact current 一致。
  - `db/fresh_schema/labor_union_fresh_current.sql`
  - `db/fresh_schema/labor_union_fresh_current.json`
  - `db/schema_assembly/labor_union_fresh_table_retirements_v1.json`
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`
  - `db/schema_parts/218_weekly_report_metrics.sql` (fresh bootstrap owner)
  - `db/cutover_releases/labor_union_validation_schema_v1.json`
  - `db/releases/labor_union_validation_schema_v1.sql`
  - `db/releases/labor_union_validation_schema_registry_guards_v1.sql` — current registry-guard successor source snapshot.
  - `db/releases/labor_union_validation_schema_finance_case_accounting_v1.sql` — preserved v57 predecessor snapshot with historical accounting marker metadata.
  - `db/releases/labor_union_validation_schema_accounting_differences_v1.sql` — current v58 full source snapshot with owner-specific noncash events, amount modes and frozen government period balances; preserve artifact 1064 and its canonical descriptor/qualification are schema-only, no business backfill.

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
