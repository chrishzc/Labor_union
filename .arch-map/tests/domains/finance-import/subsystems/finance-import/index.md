subsystem: finance-import
parent_domain: finance-import
architecture: ../../../../../domains/finance-import/subsystems/finance-import/index.md
test_root: tests/domains/finance-import/subsystems/finance-import/
integration_root: tests/domains/finance-import/subsystems/finance-import/integration/
integration_root: tests/test_finance_import_batch_job_outcome_route.py
fixtures_root: tests/fixtures/

modules:
  finance-import-correction:
    layout_status: custom_current
    test_root: ui_react/src/tests/finance_import_correction_client.test.ts

# Routing notes
Current owner-local coverage includes format detection, normalization, bank adapters, application/boundary behavior, dry-run, heuristic receipt matching, ingestion, orchestration, query, reprocessing, staging, correction contracts, and the owning-domain composite used to dispatch reviewed Finance Import candidates to registered owner ports. Relocation-sensitive schema/audit tests and cross-domain, UI, durable-job, or disposable-MySQL verification remain at their higher test boundaries. Tests owned by Case Import or another Domain must use that owner's architecture root rather than recreating a generic `tests/imports/` bucket.

# Placement refresh — 2026-09-09
The following pure Finance Import rule tests now live directly under `tests/domains/finance-import/subsystems/finance-import/`:
- `test_finance_transaction_fingerprint.py` — normalized bank-fact deduplication fingerprint.
- `test_finance_transaction_classifier.py` — deterministic transaction classification using supplied identity maps.

Both directly test `domains.finance_import`; classification labels are not evidence of a cross-owner workflow. Their test contents are unchanged. This bounded correction supersedes the earlier blanket flat-test audit claim; it does not assert that all remaining flat tests have been audited. Existing higher-boundary exceptions remain unchanged.
