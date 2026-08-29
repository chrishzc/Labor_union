subsystem: finance-import
parent_domain: finance-import
architecture: ../../../../../domains/finance-import/subsystems/finance-import/index.md
test_root: tests/domains/finance-import/subsystems/finance-import/
integration_root: tests/domains/finance-import/subsystems/finance-import/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes format detection, normalization, bank adapters, application/boundary behavior, dry-run, heuristic receipt matching, ingestion, orchestration, query, reprocessing, staging, and correction contracts. Relocation-sensitive schema/audit tests and cross-domain, UI, durable-job, or disposable-MySQL verification remain at their higher test boundaries. Tests owned by Case Import or another Domain must use that owner's architecture root rather than recreating a generic `tests/imports/` bucket.
