# Module: local-database-additive-upgrade

## Parent
- boundary: `Global migration governance`

## Responsibility
提供 local preserved-data ordered additive upgrade 的唯讀 schema 分類、資格檢查、backup、apply、journal 與 exact readback；不擁有任何 Domain schema 或 business rule。

## Implementation
- primary: `scripts/migrate_preserved_database_additive_schema.py`
- transport: `scripts/update_local_database.py`

## Verification
- integration_root: `tests/test_local_database_additive_runner.py`

## Provenance
- Existing flat test is a higher-boundary migration/developer-upgrade contract — `architecture_declared` — `.arch-map/index.md` verification routing.

## Change triggers
- Reconcile when the local upgrade entrypoint, release-state classifier, qualification, backup/apply boundary, journal, or canonical higher-boundary test changes.
