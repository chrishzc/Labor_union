# Module: preserved-database-upgrade

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
對既有 development database 建立零寫入 ordered plan，並在既有正式 release／descriptor
邊界內協調 preserve-data candidate、additive progression、replacement verification與resume；
不得修改 source root facts或繞過非schema data-effect。

## Implementation
- primary:
  - `scripts/migrate_preserved_database_additive_schema.py`
  - `scripts/local_database_additive_update.py`
  - `scripts/update_local_database.py`
  - `scripts/collect_local_additive_engine_evidence.py`
  - `shared_kernel/migration_release.py`
- entrypoints:
  - `scripts/launchers/update_local_database.bat`
  - `scripts/launchers/update_local_database.sh`
- config:
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`
  - `db/cutover_releases/labor_union_validation_schema_v1.json`
  - `db/releases/labor_union_validation_schema_v1.sql`
  - `db/schema_parts/212_government_subsidy_return_excess_recovery.sql` (fresh bootstrap owner)
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql` (fresh bootstrap successor)
- current Task 96 release successor:
  - `db/schema_parts/1024_task96_line_identity_revocation_role_binding_fk.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.descriptors.json`
  - `db/schema_parts/1025_task96_government_subsidy_return_excess_recovery.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.descriptors.json`
  - `db/schema_parts/1026_task96_scheduling_service_day_attachment_kind.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.descriptors.json`
  - `db/schema_parts/1027_historical_order_pairing_resolution_reused.sql`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.descriptors.json`
  - `db/schema_parts/1028_historical_service_accounting.sql`
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.descriptors.json`

## Contracts
- Source read-only、candidate identity、release classification、backup／journal／resume及
  replacement boundary — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/`
- integration_root: `tests/test_collect_local_additive_engine_evidence.py`
- integration_root: `tests/test_order_lifecycle_pending_status_constraint_schema.py`

## Provenance
- Preserve-data upgrade is a Global Migration capability distinct from fresh reset —
  `architecture_declared` — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- Current runner and launchers implement the bounded developer workflow — `source_observed` —
  `scripts/update_local_database.py`

## Change triggers
- Reconcile when source／candidate policy、ordered release classification、backup／journal／resume、
  replacement planning、launcher routing or canonical verification roots change.
