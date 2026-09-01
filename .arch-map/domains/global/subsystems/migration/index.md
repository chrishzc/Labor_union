# Subsystem: migration

## Parent
- domain: `global`

## Responsibility
提供 canonical fresh bootstrap、preserve-data ordered upgrade、release／descriptor
qualification、candidate verification 與 developer-local DB maintenance boundaries。

## Modules
- `local-database-fresh-reset` — explicit local canonical empty-schema reset；path:
  `modules/local-database-fresh-reset.md`
- `preserved-database-upgrade` — preserve-data candidate、ordered release classification與
  developer-local upgrade／replacement planning；path: `modules/preserved-database-upgrade.md`
- `task96-owner-contract-successors` — Task 96 owner-specific additive roots／exact lineage
  terminal release；path: `modules/task96-owner-contract-successors.md`
- `task97-production-script-governance` — Task 97 production-script inventory與guard evidence；path: `modules/task97-production-script-governance.md`

## Contracts
- Fresh bootstrap 與 preserve-data upgrade 分離；source／candidate／receipt／release
  identity fail closed —
  `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`

## Verification routing
- default_boundary: Module
- test_root: `tests/domains/global/subsystems/migration/`
- integration_root: `tests/domains/global/subsystems/migration/integration/`
