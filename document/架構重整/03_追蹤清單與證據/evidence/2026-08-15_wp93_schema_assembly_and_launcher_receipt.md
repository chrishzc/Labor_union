# WP93 Schema Assembly and Local Launcher Receipt

- date: 2026-08-15
- authorization: 使用者明確要求完成 WP93，並實測 local update 與 development launcher
- source database: 去敏本機測試資料庫 `lu_test_dataset_contract_signing_v4`
- release: `labor-union-schema-assembly-2026-08-15-v1`
- data boundary: 無正式資料、無外部 provider、無 raw dump 或 credential 寫入本 receipt

## Gate results

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | `93_Schema_Assembly_and_Migration_Archive_Retirement_Work_Package.md` |
| Change inventory | PASS | 199 fresh retirement action、999 view-only release；無 system seed／business-row backfill |
| Static release | PASS | focused: `71 passed` |
| Descriptor | PASS | view contract unit coverage；descriptor hash and artifact hash loaded by release manifest |
| Read-only plan | PASS | `python -m scripts.update_local_database` preview `parts_to_apply=[]`; `--require-current` current |
| Engine verification | PASS | fresh bootstrap; WP78/WP84 candidate integration `7 passed`; missing-view source → candidate semantic `exact` |
| Developer acceptance | PASS | `update_local_database.bat --dry-run` and `start_local_development.bat --smoke-test` exit 0 |

## Commands and results

1. Focused static suite:
   `python -m pytest tests/test_schema_assembly.py tests/test_init_db_schema_parts.py tests/test_bootstrap_disposable_mysql_schema.py tests/test_verify_validation_schema_manifest.py tests/test_preserved_database_plan_contract.py tests/test_field_authority_legacy_name_audit.py tests/test_launcher_dry_run.py tests/test_local_development_launcher_smoke.py -q` → `71 passed`.
2. Fresh engine path:
   `python -m scripts.bootstrap_disposable_mysql_schema --database lu_test_wp93_fresh_v2_20260815 --confirm-database lu_test_wp93_fresh_v2_20260815` → 114 active artifacts and final object postcheck passed.
3. Preserve candidate path:
   `MYSQL_TEST_CONTAINER=mysql_db python -m pytest tests/test_wp78_partial_recovery_disposable_mysql.py tests/test_wp84_legacy_knowledge_empty_recovery.py -q -m integration` → `7 passed`; tests clean their `lu_test_wp78_*` and `lu_test_wp84_*` databases.
4. View release candidate path:
   a full-chain disposable copy with `v_order_details` removed was dumped, restored to a candidate, and applied with the new 999 release. The result was `backfilled` and the candidate descriptor state was `exact`; both temporary `lu_test_wp93_view_*` databases were removed afterwards.
5. Local operator paths:
   `update_local_database.bat --dry-run` ran preflight then canonical preview; `start_local_development.bat --smoke-test` reported API and Streamlit health, started local monitor/file watcher/durable/incident workers, then cleaned them up.

## Result

`DB_CHANGE_READY` for the WP93 schema-assembly scope. The warning-center and import business work remain outside this receipt.
