# Test Module: case-preference-manual

## Canonical roots
- layout_status: custom_current
- layout_basis: `.arch-map/tests/index.md` permits documented frontend test exceptions; the canonical Staff component oracle remains under `ui_react/src/tests/` and the owner Python oracles remain under the Staff module test root.
- tests/domains/staff/subsystems/staff/modules/case-preference-manual/
- ui_react/src/tests/domains/staff/subsystems/staff/modules/case-preference-manual/

## Oracles
- Query/Preview perform no writes; Apply parent-locks before relation locks.
- Fresh snapshot and preview fingerprints reject stale Apply; receipt replay is idempotent and payload conflict is typed.
- The six writable relations preserve detail values; transportation remains a seventh read-only/source_not_ready fact.
