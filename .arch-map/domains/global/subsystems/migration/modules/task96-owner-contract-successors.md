# Module: task96-owner-contract-successors

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
以單一 additive terminal successor release 保存已核准的 Client Profile、Case Import、
Payroll、Finance Import 與 Government Subsidy owner-specific root／event／receipt／exact
lineage；不回填、不推測或改寫既有 business roots。

## Implementation
- primary: `db/schema_parts/1021_task96_owner_contract_successors.sql`
- release:
  - `db/migration_releases/labor_union_2026_08_31_task96_owner_contract_successors_v1.json`
  - `db/migration_releases/labor_union_2026_08_31_task96_owner_contract_successors_v1.descriptors.json`
- composition:
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`
  - `db/cutover_releases/labor_union_validation_schema_v1.json`
- validator: `scripts/migrate_preserved_database_additive_schema.py`

## Verification
- test_root: `tests/domains/global/subsystems/migration/modules/task96-owner-contract-successors/`
- higher-boundary baseline propagation remains at the flat paths declared by `.arch-map/index.md`.

## Change triggers
- Reconcile when any owned table／parent-column contract、release hash、terminal artifact、
  fresh assembly order or preserve-data descriptor changes.
