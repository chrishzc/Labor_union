module: liff-configuration
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/liff-configuration.md
test_root: tests/domains/external-integration/subsystems/line/modules/liff-configuration/

# Tests: liff-configuration

## Owner
- domain: `external-integration`
- subsystem: `line`
- module: `liff-configuration`
- source_map: `.arch-map/domains/external-integration/subsystems/line/modules/liff-configuration.md`

## Roots
test_root: tests/domains/external-integration/subsystems/line/modules/liff-configuration/

## Oracle
Database SSOT for runtime, page/theme/field writes, stale conflicts, immutable history/rollback and no file or external effects. Native MySQL tests require an explicitly selected localhost development database; disposable databases and the `lu_test_*` prefix are not mandatory, and `union_db` is allowed under specification 10 §9.1 with scenario-owned writes and before/after evidence.
