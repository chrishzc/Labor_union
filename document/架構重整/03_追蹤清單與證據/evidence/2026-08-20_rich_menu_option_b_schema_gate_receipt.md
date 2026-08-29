# Rich Menu publication Option B schema gate receipt

- Date: 2026-08-20
- Work Package: `PROV-20260817-react-admin-phase4c-line-richmenu-publication-mutation-work-package.md`
- Approval: 使用者明確核准 Option B；只允許 additive schema/release artifacts 與 disposable MySQL 驗證。
- Follow-up authorization: 使用者其後允許將 additive migration 套用目前 DB；仍須通過非 root 身分與 preserve-data gates，未授權繞過根規範直接使用 root。
- Base: `main` at `f9240b9e3abbcf665b5c979e0973f675197d8494`; existing dirty paths preserved。
- Canonical artifact: `db/schema_parts/1001_line_rich_menu_publication_step_saga.sql`
- Release: `labor-union-line-rich-menu-publication-step-saga-2026-08-20-v1`
- Data effect: `schema_only`; business backfill `0`; system seed `0`; destructive change `0`。
- Legacy compatibility: `line_rich_menu_publication_step_receipts` is retained unchanged。

## Frozen table contract

1. `line_rich_menu_publication_step_acknowledgements`: immutable acknowledged `create/upload/link/switch/cleanup` rows keyed by `(publication_id, step_name)` and `idempotency_key`; stores request fingerprint, provider menu ID and acknowledgement time。
2. `line_rich_menu_publication_step_attempt_events`: immutable typed provider outcomes (`success`, `rate_limited`, `rejected`, `unavailable`, `timeout`, `lost_ack`) keyed by `(publication_id, step_name, attempt_number)` and `idempotency_key`; stores request fingerprint, bounded provider ID/error code, correlation and attempt time。
3. `line_rich_menu_publication_cleanup_anomalies`: immutable cleanup anomaly rows keyed by `idempotency_key`; stores publication, request fingerprint, bounded error code and occurrence time。

All three tables use restrictive FK references to `line_rich_menu_publication_tasks(id)`, explicit indexes and checks, and update/delete blocking triggers. No table alteration, legacy receipt copy, insert seed, row backfill or destructive operation is present in the schema part.

The release descriptor persists all 11 indexes, 3 foreign keys and 7 checks. The canonical runner compares these contracts against the schema SQL before using the full metadata comparator. It distinguishes `absent/exact/partial/drift`; partial or drift blocks migration. Legacy v1 descriptors that only declare tables/triggers/views retain presence-only behavior and their released bytes/hashes are unchanged; partial metadata declarations fail closed.

## Gate results

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | User approval and WP amendment, Option B exact table scope |
| Change inventory | PASS | `schema_only`; 0 seed/backfill/destructive; legacy table retained |
| Static release | PASS | `validate_schema_assembly()` and `verify_manifest()` returned no errors; manifest/descriptor hashes load successfully |
| Descriptor | PASS | persisted descriptor and canonical SQL agree on 11 indexes, 3 FK, 7 checks; canonical comparator also checks full columns and 6 immutable triggers; four-state focused test passed |
| Read-only plan | NOT_RUN | No safe non-root disposable source configuration; existing `.env` target is configured with root only and was not used |
| Engine verification | BLOCKED | `LABOR_UNION_TEST_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` and `MYSQL_USER` are unset; Docker `mysql_db` is running, but no non-root credential is available; no candidate could be opened safely |
| Developer acceptance | NOT_RUN | Current-DB additive application is authorized but blocked before plan/engine gates by missing non-root credentials; no `union_db`, production DB or `--switch` operation |

## Commands

- Current static release/plan suite: `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/rich-menu-option-b-current-db-static -q tests/line/infrastructure/test_line_rich_menu_publication_schema_option_b.py tests/test_schema_assembly.py tests/test_preserved_database_plan_contract.py tests/test_migrate_preserved_database_additive_schema_cli.py` → `42 passed`；未連線或修改任何DB。
- Frozen-base final integration suite: `.venv\Scripts\python.exe -m pytest tests/line/subsystems/test_line_rich_menu_publication_snapshot.py tests/line/subsystems/test_line_rich_menu_publication_public_contract.py tests/line/subsystems/test_line_rich_menu_binding.py tests/line/infrastructure/test_line_rich_menu_provider_saga.py tests/line/infrastructure/test_line_mysql_repositories.py tests/test_line_rich_menu_publication_route.py tests/line/infrastructure/test_line_rich_menu_publication_schema_option_b.py tests/test_preserved_database_plan_contract.py tests/test_preserved_database_additive_upgrade_cutover.py tests/test_admin_auth_runtime.py --basetemp .pytest_tmp/rich-menu-final-integration-frozen -q` → `149 passed, 1 skipped`。Skip為需要安全disposable MySQL的engine案例；未連線或修改任何DB。
- Descriptor／plan／assembly focused suite: `81 passed, 1 skipped`; covers 11/3/7 equality, descriptor drift fail closed, `absent/exact/partial/drift`, release plan and assembly contracts。
- `.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/rich-menu-option-b-schema2 -q tests/line/infrastructure/test_line_rich_menu_publication_schema_option_b.py tests/test_schema_assembly.py tests/test_preserved_database_plan_contract.py` → `36 passed`。
- `.venv\\Scripts\\python.exe scripts/build_validation_schema_release.py --check` → pass。
- `load_migration_release_manifest(...)` → pass。
- `scripts.sql_statements.split_sql(1001...)` → 15 statements parsed。
- `docker info --format '{{.ServerVersion}}'` → `29.7.2`；`docker ps` confirms `mysql_db` is running；未使用 root 或執行 MySQL command。

Conclusion: `DB_CHANGE_NOT_READY` until a non-root, disposable `lu_test_*` MySQL configuration is explicitly available and fresh/preserve candidate verification completes. The current `.env` target is `lu_test_dataset_contract_signing_v4` with root-only credentials; no DB write occurred. Queued／publishing tasks must drain before worker cutover; otherwise the legacy worker remains until terminal。

## Historical pre-recovery G4 reconciliation（2026-08-20）

Current verified agent evidence records the final G4 suite as `150 passed, 1 skipped`; the preceding Phase 3–6 integration
suite was `149 passed, 1 skipped`, followed by the G4 additions. This receipt update did not rerun either suite. The skip
remains the disposable MySQL engine case; no DB was opened or modified.

Production paths：`api/routes/line_rich_menus.py`、`api/schemas/line_rich_menus.py`、
`subsystems/line/rich_menu_contracts.py`、`subsystems/line/rich_menu_application.py`、
`subsystems/line/rich_menu_publication_workflow.py`、`subsystems/line/rich_menu_worker.py`、
`subsystems/line/ports.py`、`infrastructure/mysql/line_configuration_publication_repository.py`、
`infrastructure/line/rich_menu_api_adapter.py`。
Test paths：`tests/line/subsystems/test_line_rich_menu_publication_snapshot.py`、
`tests/line/subsystems/test_line_rich_menu_publication_public_contract.py`、
`tests/line/infrastructure/test_line_rich_menu_provider_saga.py`、
`tests/test_line_rich_menu_publication_route.py`、`tests/line/infrastructure/test_line_rich_menu_publication_schema_option_b.py`。

### Seven audit dispositions

| Audit item | Disposition | Current evidence／boundary |
|---|---|---|
| Step attempt event is durable | PASS | worker appends typed attempt events and repository persists them; provider saga tests assert outcomes |
| TIMEOUT／UNAVAILABLE／LOST_ACK resume | PASS with bounded cleanup scope | main step unknown exception maps to retryable `UNAVAILABLE` while preserving `LOST_ACK`; cleanup exception preserves `LOST_ACK` and anomaly, and cleanup-only claim redrives without republishing |
| Alias 409 semantics | PASS | adapter GETs current alias; same target is idempotent, different target returns typed `line_rich_menu_alias_target_conflict` |
| Required reason／idempotency／correlation | PASS | closed Pydantic requests reject blank/missing metadata; route forwards caller values and does not synthesize them |
| Strict mutation response | PASS for publication mutations; deferred legacy media upload | publish／retry use closed typed responses and dedicated public-contract test; legacy image upload `BaseResponse[dict]` is outside publication mutation contract and is not claimed hardened here |
| Published commit／cleanup crash redrive | PASS | published record commit precedes cleanup; cleanup failure／crash emits a typed anomaly, and a cleanup-only claim redrives cleanup without republishing or rolling back published state |
| Pagination beyond 100 rows | PASS | typed repository uses COUNT plus SQL LIMIT/OFFSET; `page_size <= 100` bounds a page, while totals/pages support rows beyond 100 (route characterization uses total 243) |

Additional current worker audit：the previously reported generic `_run_step` `LOST_ACK`＋terminal `REJECTED` mismatch is
resolved in the current bytes by returning retryable `UNAVAILABLE`; cleanup-only manual anomaly remains a bounded operational
path and is not a publication failure. This is not a claim of real-provider or engine readiness.

Historical gate summary：G0-G6 PASS；G7 PASS with the recorded engine skip；G8 evidence boundary PASS。At that time the DB gate remained
`DB_CHANGE_NOT_READY` because read-only plan is `NOT_RUN` and engine verification is `BLOCKED` without a safe non-root
disposable MySQL environment. Work Package status remains `in-progress` until that gate is independently completed。

## Current state update（2026-08-21；supersedes the pre-recovery gate summary above）

The earlier gate table records the pre-recovery state. The approved local recovery has now completed and is evidenced by
the prepared-replacement verification receipt（原始低頻 evidence 已自目前工作樹移除，可由 Git 歷史精準取回）。

| Current assertion | Status | Evidence |
|---|---|---|
| Source Option B schema exactness | PASS | Source and preserved candidate each have `3 tables / 11 indexes / 3 foreign keys / 7 checks / 6 immutable triggers`; legacy step-receipt table retained。 |
| Candidate preservation | PASS | Candidate dump/database remain hash-exact and were not rebuilt, deleted or rewritten。 |
| Rich Menu drain | PASS | Source and candidate both report `queued=0`, `publishing=0`。 |
| Prepared replacement recovery | PASS | Recovery exit `0`, restore `21.226s`, terminal replacement receipt `completed`；schema reapply／seed／backfill／destructive counts are `0`。 |
| Qualified additive read-only preview | PASS | 歷史 fast preview output（未納入 Git）：`current / daily_additive / exact`，`5.633s` within the `30s` guard，zero write。 |
| Fast preview `<=5s` UX target | BLOCKED | Current preview is `5.633s`; mandatory `30s` safety guard still passes。 |
| Pending additive apply | NOT_RUN | No pending additive release was applied；the fast updater developer-acceptance apply remains unverified。 |

Current Option B schema/recovery DB gates are `PASS` for the approved local scope. The separate fast-additive acceptance
remains `NOT_RUN`; this receipt does not authorize production, `union_db`, `--switch`, candidate cleanup, or real-provider use。
