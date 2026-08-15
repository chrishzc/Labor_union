---
doc_type: evidence-receipt
declared_status: completed
date: 2026-08-15
owner: Staff / Matching / Scheduling
scope: WP91 Staff retirement implementation closeout evidence
---

# WP91 Staff retirement focused implementation receipt

## Delivered scope

- Independent `staff_lifecycle_states` projection, immutable lifecycle events, global command claims, and idempotent apply receipts.
- Admin Query/Preview/Apply API for retirement and reactivation.
- Matching candidate, availability, notification, interaction, schedule confirmation, and Assignment Plan lifecycle guards.
- Canonical schema artifact `1000_staff_retirement.sql`, fresh assembly catalog, descriptor, and release-chain manifest.

## Evidence

| Check | Status | Evidence |
|---|---|---|
| Focused lifecycle, consumer, schema, and bootstrap tests | PASS | `.venv\Scripts\python.exe -m pytest tests/test_staff_retirement_workflow.py tests/test_staff_retirement_consumer_guards.py tests/test_init_db_schema_parts.py tests/test_bootstrap_disposable_mysql_schema.py -q` → `24 passed` |
| Release-chain read-only plan | PASS | `.venv\Scripts\python.exe -m scripts.update_local_database` → `status: preview`, `release_id: labor-union-staff-retirement-2026-08-15-v1`, `parts_to_apply: [1000_staff_retirement.sql]` |
| Static release/descriptor | PASS | `db/schema_assembly/labor_union_fresh_schema_v1.json`, `db/migration_releases/labor_union_2026_08_15_staff_retirement_v1.json`, and descriptor are mutually referenced |
| Fresh bootstrap disposable MySQL | PASS | `lu_test_wp91_fresh_r2` contains all three lifecycle tables; validation manifest object postcheck returned no errors |
| Preserve-data source → candidate → verify | PASS | `lu_test_dataset_contract_signing_v4_wp91_r2` receipt is `verified`; `1000_staff_retirement.sql=exact` and source/candidate data evidence match |
| Developer local database acceptance | PASS | Authorized `.venv\\Scripts\\python.exe -m scripts.update_local_database --apply --mysql-container mysql_db --candidate-database lu_test_dataset_contract_signing_v4_wp91_accept --confirm-database lu_test_dataset_contract_signing_v4` completed; source backup, candidate verification, replacement, and post-replacement exactness succeeded; `union_db` was not operated |

## DB change conclusion

All required WP91 DB change gates are `PASS`. The developer-local source `lu_test_dataset_contract_signing_v4` was backed up, replaced only after candidate verification, and post-replacement verification reported `1000_staff_retirement.sql=exact`; the final operation status was `completed`.

This receipt is not production deployment, cutover, or production-data authorization. No backfill, seed, or external notification was performed, and `union_db` was not operated.

## Archive evidence

- Final receipt directory: `scratch/local_database_updates/lu_test_dataset_contract_signing_v4_wp91_accept/`.
- Source backup: `source.sql`; candidate export: `candidate.sql`; replacement and operation receipts are retained locally for rollback/audit.
- Restore trigger: a failed lifecycle schema regression, a preservation mismatch, or an operator-requested rollback of the developer-local database.