subsystem: finance-import
parent_domain: finance-import
architecture: ../../../../../domains/finance-import/subsystems/finance-import/index.md
test_root: tests/domains/finance-import/subsystems/finance-import/
integration_root: tests/domains/finance-import/subsystems/finance-import/integration/
fixtures_root: tests/fixtures/

# Routing notes
Current owner-local coverage includes format detection, normalization, bank adapters, application/boundary behavior, dry-run, heuristic receipt matching, ingestion, orchestration, query, reprocessing, staging, correction contracts, and the owning-domain composite used to dispatch reviewed Finance Import candidates to registered owner ports. Relocation-sensitive schema/audit tests and cross-domain, UI, durable-job, or disposable-MySQL verification remain at their higher test boundaries. Tests owned by Case Import or another Domain must use that owner's architecture root rather than recreating a generic `tests/imports/` bucket.

# Flat-test audit
The current flat-test audit found no additional high-confidence Finance Import owner-local tests outside the documented relocation-sensitive, cross-domain, UI, durable-job, migration/schema, disposable-MySQL/E2E, or other-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
