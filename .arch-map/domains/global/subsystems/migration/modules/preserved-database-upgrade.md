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
- entrypoints:
  - `scripts/launchers/update_local_database.bat`
  - `scripts/launchers/update_local_database.sh`
- config:
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`

## Contracts
- Source read-only、candidate identity、release classification、backup／journal／resume及
  replacement boundary — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/`

## Provenance
- Preserve-data upgrade is a Global Migration capability distinct from fresh reset —
  `architecture_declared` — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- Current runner and launchers implement the bounded developer workflow — `source_observed` —
  `scripts/update_local_database.py`

## Change triggers
- Reconcile when source／candidate policy、ordered release classification、backup／journal／resume、
  replacement planning、launcher routing or canonical verification roots change.
