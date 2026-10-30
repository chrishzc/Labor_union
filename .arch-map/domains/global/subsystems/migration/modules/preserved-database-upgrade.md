# Module: preserved-database-upgrade

## Parent
- domain: `global`
- subsystem: `migration`

## Responsibility
對既有 development database 建立零寫入 ordered plan，並在既有正式 release／descriptor
邊界內協調 preserve-data candidate、additive progression、replacement verification與resume；
不得修改 source root facts或繞過非schema data-effect。

## Implementation
- `db/schema_parts/240_order_reopen_reason_optional.sql`、`db/schema_parts/1062_order_reopen_reason_optional.sql`、`db/migration_releases/labor_union_2026_10_29_order_reopen_reason_optional_v1.json` 及同名 descriptors；fresh bundle 為 `db/releases/labor_union_validation_schema_order_reopen_reason_v1.sql` — 只移除重開事件複合 CHECK 的人工備註非空條件，保留命令、actor、correlation 與其他 guards；精確舊定義 pending、新定義 exact，缺少或未知定義 fail closed，所有既有列不變。Metadata contract 沿本 Module test root，業務空白備註寫入沿 Orders cancellation 的既有跨 owner MySQL integration test。
- `db/schema_parts/239_matching_manual_reason_optional.sql`／`db/schema_parts/1061_matching_manual_reason_optional.sql`、`db/migration_releases/labor_union_2026_10_29_matching_manual_reason_optional_v1.json` 及同名 descriptors；fresh bundle 為 `db/releases/labor_union_validation_schema_matching_manual_reason_v1.sql` — 移除已退役的人工媒合原因非空 CHECK，保留歷史列與其餘約束。原定義精確比對才 pending，已移除 exact，未知定義或 parent drift 停止；fresh／preserve 交易驗收在 matching-coordination integration root，metadata contract 在本 Module test root。
- `db/schema_parts/1060_registry_case_deletion_guards.sql`、`db/migration_releases/labor_union_2026_10_29_registry_case_deletion_guards_v1.json` 及同名 descriptors — 精確替換 129 個保護 trigger，保留原始 default guard；僅 root 未簽約案件的 active claim scope 可刪除。歷史 release 比較僅將完整匹配的 successor 投影為 predecessor，未知改寫仍為 drift。
- `validation/receipts/PROV-REGISTRY-GUARDS-local-additive-qualification-20261029.json` — fresh／含簽回與未簽回資料的 preserve candidate 證據；實際 source apply 另建 release-scoped 備份。
- `db/schema_parts/237_non_citizen_case_sequences.sql`／`1059_non_citizen_case_sequences.sql`、`db/migration_releases/labor_union_2026_10_29_non_citizen_cases_v1.json` 及同名 descriptors — 核准交易內的非市民年度流水；schema-only，無既有案件回填；fresh／preserve 驗證由 Case Import integration owner 承接。
- `validation/receipts/PROV-RD1058-local-additive-qualification-20261029.json` — exact enum append qualification from synthetic fresh／preserve evidence; local apply still creates its own release-scoped backup.
- `validation/receipts/PROV-NON-CITIZEN-CASES-local-additive-qualification-20261029-restart-0951db92f6.json` — 1059 exact v53 fresh boundary plus native preserved candidate; future registry guards are absent at this qualification boundary.
- `validation/receipts/PROV-REGISTRY-CASE-GUARDS-local-additive-qualification-20261029-restart-0951db92f6.json` — 1060 corrected guarded triggers, complete fresh and native preserved-data evidence; selectable explicitly when multiple valid proofs exist.
- `db/migration_releases/labor_union_2026_10_29_client_refund_overage_receipt_v1.json`, `db/migration_releases/labor_union_2026_10_29_client_refund_overage_receipt_v1.descriptors.json` — existing Client Finance writer's missing receipt enum value; recognizes exact three-value predecessor and four-value successor, preserves existing records.
- `db/migration_releases/labor_union_2026_10_29_finance_statement_workspace_v1.json`, `db/migration_releases/labor_union_2026_10_29_finance_statement_workspace_v1.descriptors.json` — additive archive commands, manual statements, identity-only exclusions and accounting acknowledgements; byte-equivalent fresh 235 / preserve 1057, no accounting backfill.
- Accounting pricing additive release: `db/schema_parts/234_accounting_pricing.sql`, `db/schema_parts/1056_accounting_pricing.sql`, `db/migration_releases/labor_union_2026_10_29_accounting_pricing_v1.json` and `db/migration_releases/labor_union_2026_10_29_accounting_pricing_v1.descriptors.json`; no legacy finance backfill.
- Accounting pricing evidence: `validation/receipts/ACCOUNTING-PRICING-implementation-20261029.json` — synthetic fresh/preserve and implementation verification; shared-workspace failures are explicit.
- subsidy policy replay successor: `db/migration_releases/labor_union_2026_10_29_subsidy_policy_replay_v4.json`、`db/migration_releases/labor_union_2026_10_29_subsidy_policy_replay_v4.descriptors.json` — 同時保留不限名稱前綴的人工裁決；preservation 依來源已提交 marker 保持既有身分，Finance version 只計本次新增 policy events；不改業務 writer 或回填規則。
- subsidy policy database-name successor: `db/migration_releases/labor_union_2026_10_29_subsidy_policy_database_names_v3.json`、`db/migration_releases/labor_union_2026_10_29_subsidy_policy_database_names_v3.descriptors.json` — 依 2026-10-29 人工裁決移除 `lu_test_` 名稱限制；其餘本機環境／plan／backup gate 保留，v2 manifest 保留歷史。
- subsidy period policy: `scripts/migrate_subsidy_period_policy.py` — hash-bound one-time identity relabeling and replayable automatic-refund synchronization, selected by the default preserve-data route. Plan binds selected backfill inventory; invalid owner facts remain pending with case/reason evidence, including after verify or replay. Business backfills select the preserve route before schema-only qualification.
- subsidy period hash successor: `db/migration_releases/labor_union_2026_10_27_government_subsidy_periods_hash_v2.json` and `db/migration_releases/labor_union_2026_10_27_government_subsidy_periods_hash_v2.descriptors.json` bind the unchanged 1055 SQL and unchanged policy backfill. The archived 2026-10-24 v1 manifest is excluded from default selection; schema, runtime grants and business behavior are unchanged. Preserve-data classification shares the approved fresh retirement projection, retaining the existing LINE append-only/successor contracts.
- primary:
  - `db/schema_parts/1053_line_order_group_invitation_url.sql` — nullable 私有群組網址，無資料回填。
  - `db/migration_releases/labor_union_2026_10_22_line_order_group_invitation_url_v1.json`
  - `db/migration_releases/labor_union_2026_10_22_line_order_group_invitation_url_v1.descriptors.json`
  - `validation/receipts/PROV-L07-GROUP-INVITATION-local-additive-qualification-20261022.json` — synthetic MySQL fresh／preserve qualification；既有綁定與成員歷史保留，網址保持 NULL，無 provider effect。
  - `db/schema_parts/1052_nas_registration_approval.sql` — additive 申請快照、版本及核准欄位；不回填既有客戶／表單。
  - `db/migration_releases/labor_union_2026_10_19_nas_registration_approval_v1.json`
  - `db/migration_releases/labor_union_2026_10_19_nas_registration_approval_v1.descriptors.json`
  - `db/schema_parts/232_candidate_weekly_information.sql` — fresh 候選週說明補充事件。
  - `db/schema_parts/1051_candidate_weekly_information.sql` — preserve schema-only；只在 enum 尾端新增值，舊 ordinal／事件不變。
  - `db/migration_releases/labor_union_2026_10_14_candidate_weekly_information_v1.json`
  - `db/migration_releases/labor_union_2026_10_14_candidate_weekly_information_v1.descriptors.json`
  - `db/schema_parts/231_staff_union_number.sql` — fresh Staff manual number，nullable binary text 與 unique index。
  - `db/schema_parts/1050_staff_union_number.sql` — schema-only preserve upgrade，既有人員保持 NULL。
  - `db/migration_releases/labor_union_2026_10_13_staff_union_number_v1.json`
  - `db/migration_releases/labor_union_2026_10_13_staff_union_number_v1.descriptors.json` — 必驗 column charset／collation 與 full-column unique index，partial／drift fail closed。
  - `scripts/migrate_preserved_database_additive_schema.py`
  - `scripts/fresh_schema_policy.py` — descriptor comparator 僅排除正式退役的 table-owned objects；舊表 present/absent 均不要求 DDL，保留物件仍嚴格驗證。
  - `scripts/local_database_additive_update.py`
  - `scripts/update_local_database.py`
  - `scripts/collect_local_additive_engine_evidence.py` — library-only；沒有獨立命令入口。
  - `shared_kernel/migration_release.py`
- entrypoints:
  - `scripts/launchers/update_local_database.bat`
  - `scripts/launchers/update_local_database.sh`
  - `deployment/nas/upgrade-database.sh` and `scripts/update_nas_database.py` — DSM manual update adapter; `--update` runs prepare → verified switch → same-project activation under one lock. Advanced prepare/switch modes remain available. The stopped operational volume is never mounted; a checksum-verified cold backup is copied into a new volume, then the existing localhost/development updater runs only in its isolated helper namespace. Switching preserves the original volume, database name, credentials and all non-image deployment env bytes. See owner spec §9.4 and `deployment/nas/DATABASE-UPGRADE.md`.
- config:
  - `db/schema_assembly/labor_union_fresh_table_retirements_v1.json` — current 逐表決策；既有表／資料不刪除。
  - `db/schema_parts/230_client_hcm_email.sql` — fresh nullable HCM email；BeClass email 獨立保存。
  - `db/schema_parts/1049_client_hcm_email.sql` — schema-only preserve-data email upgrade，無 backfill。
  - `db/migration_releases/labor_union_2026_10_13_client_hcm_email_v1.json`
  - `db/migration_releases/labor_union_2026_10_13_client_hcm_email_v1.descriptors.json`
  - `validation/receipts/PROV-HCM-EMAIL-local-additive-qualification-20261013.json` — synthetic MySQL fresh／preserve qualification；舊 Client／BeClass 資料保留，主檔新 email 為 NULL。
  - `db/schema_parts/1048_order_cancellation_optional_downstream.sql` — cancellation receipt optional downstream owners。
  - `db/schema_parts/229_order_cancellation_optional_downstream.sql` — fresh bootstrap successor。
  - `db/migration_releases/labor_union_2026_09_29_order_cancellation_optional_downstream_v1.json`
  - `db/migration_releases/labor_union_2026_09_29_order_cancellation_optional_downstream_v1.descriptors.json`
  - `db/schema_assembly/labor_union_fresh_schema_v1.json`
  - `db/cutover_releases/labor_union_validation_schema_v1.json`
  - `db/releases/labor_union_validation_schema_v1.sql`
  - `db/schema_parts/212_government_subsidy_return_excess_recovery.sql` (fresh bootstrap owner)
  - `db/schema_parts/214_historical_order_pairing_resolution_reused.sql` (fresh bootstrap successor)
  - `db/schema_parts/226_service_before_replacement.sql` (MySQL 8.4-compatible fresh bootstrap successor; immutable preserve release remains 1012)
  - `db/schema_parts/1047_scheduling_buffer_advisory.sql` — schema-only；保留 buffer facts／歷史 projection；實際 interval staff/date 仍唯一。
  - `db/migration_releases/labor_union_2026_09_29_scheduling_buffer_advisory_v1.json`
  - `db/migration_releases/labor_union_2026_09_29_scheduling_buffer_advisory_v1.descriptors.json`
  - `validation/receipts/PROV-SCHEDULING-BUFFER-ADVISORY-local-additive-qualification-20260929-lf.json` — current synthetic MySQL fresh／preserve qualification；與 Git LF artifact bytes 綁定，同日實際服務仍唯一，全部歷史資料逐欄保留。
  - `validation/receipts/PROV-SCHEDULING-BUFFER-ADVISORY-local-additive-qualification-20260929.json` — immutable 初次本機驗證紀錄；已由 LF 回條取代，僅保留驗證追溯，不代表 current artifact identity。
- current Task 96 release successor:
  - `db/schema_parts/1024_task96_line_identity_revocation_role_binding_fk.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.descriptors.json`
  - `db/schema_parts/1025_task96_government_subsidy_return_excess_recovery.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.descriptors.json`
  - `db/schema_parts/1026_task96_scheduling_service_day_attachment_kind.sql`
  - `db/migration_releases/labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.descriptors.json`
  - `db/schema_parts/1027_historical_order_pairing_resolution_reused.sql`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.descriptors.json`
  - `db/schema_parts/1028_historical_service_accounting.sql`
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.json`
  - `db/migration_releases/labor_union_2026_09_01_historical_service_accounting_v1.descriptors.json`
  - `db/schema_parts/1031_weekly_report_batches.sql`
  - `db/migration_releases/labor_union_2026_09_06_weekly_report_batches_v1.json`
  - `db/migration_releases/labor_union_2026_09_06_weekly_report_batches_v1.descriptors.json`
  - `db/schema_parts/1033_matching_holiday_work_agreements.sql`
  - `db/migration_releases/labor_union_2026_09_08_matching_holiday_work_agreement_plan_version_v1.json`
  - `db/migration_releases/labor_union_2026_09_08_matching_holiday_work_agreement_plan_version_v1.descriptors.json`
  - `db/schema_parts/1035_weekly_report_metrics.sql`
  - `db/migration_releases/labor_union_2026_09_09_weekly_report_metrics_v1.json`
  - `db/migration_releases/labor_union_2026_09_09_weekly_report_metrics_v1.descriptors.json`
  - `db/schema_parts/1034_contract_external_signing_final_pdf_completion.sql`
  - `db/migration_releases/labor_union_2026_09_09_contract_external_signing_final_pdf_completion_v1.json`
  - `db/migration_releases/labor_union_2026_09_09_contract_external_signing_final_pdf_completion_v1.descriptors.json`
- current Issue 276 registry owner release:
  - `db/schema_parts/219_registry_owner_mutations.sql` (fresh bootstrap successor)
  - `db/schema_parts/1036_registry_owner_mutations.sql`
  - `db/migration_releases/labor_union_2026_09_11_registry_owner_mutations_v1.json`
  - `db/migration_releases/labor_union_2026_09_11_registry_owner_mutations_v1.descriptors.json`
- current twins Payroll policy release:
  - `db/schema_parts/220_twins_payroll_policy.sql` (fresh bootstrap successor)
  - `db/schema_parts/221_twins_payroll_order_details_view.sql` (fresh view successor)
  - `db/schema_parts/1037_twins_payroll_policy.sql`
  - `db/schema_parts/1038_twins_payroll_order_details_view.sql`
  - `scripts/backfill_twins_payroll_rate_snapshots.py`
  - `db/migration_releases/labor_union_2026_09_11_twins_payroll_policy_v1.json`
  - `db/migration_releases/labor_union_2026_09_11_twins_payroll_policy_v1.descriptors.json`
  - `db/migration_releases/labor_union_2026_09_12_twins_payroll_policy_backfill_hash_v2.json` — current preserve-chain successor; repeats the immutable 1037／1038 schema contracts and binds the audited current backfill bytes. The 2026-09-11 v1 manifest／descriptor remains archived and is intentionally excluded from default selection because its protected backfill digest no longer matches the current artifact.
  - `db/migration_releases/labor_union_2026_09_12_twins_payroll_policy_backfill_hash_v2.descriptors.json`
- current order-details owner-date successor:
  - `db/schema_parts/1043_twins_payroll_order_details_view.sql`
  - `db/migration_releases/labor_union_2026_09_15_order_details_owner_dates_v1.json`
  - `db/migration_releases/labor_union_2026_09_15_order_details_owner_dates_v1.descriptors.json`
- current order service-hours half-hour precision release:
  - `db/schema_parts/223_order_service_hours_half_precision.sql` (fresh bootstrap successor)
  - `db/schema_parts/1040_order_service_hours_half_precision.sql`
  - `db/migration_releases/labor_union_2026_09_14_order_service_hours_half_precision_v1.json`
  - `db/migration_releases/labor_union_2026_09_14_order_service_hours_half_precision_v1.descriptors.json`
- current historical manual BeClass origin release:
  - `db/schema_parts/224_historical_manual_beclass_origin.sql` (fresh bootstrap successor)
  - `db/schema_parts/1041_historical_manual_beclass_origin.sql`
  - `db/migration_releases/labor_union_2026_09_14_historical_manual_beclass_origin_v1.json`
  - `db/migration_releases/labor_union_2026_09_14_historical_manual_beclass_origin_v1.descriptors.json`
- current order-terms optional downstream versions release:
  - `db/schema_parts/227_order_terms_optional_downstream_versions.sql` (fresh bootstrap successor)
  - `db/schema_parts/1044_order_terms_optional_downstream_versions.sql`
  - `db/migration_releases/labor_union_2026_09_22_order_terms_optional_downstream_versions_v1.json`
  - `db/migration_releases/labor_union_2026_09_22_order_terms_optional_downstream_versions_v1.descriptors.json`
- current order-terms optional Scheduling receipt release:
  - `db/schema_parts/228_order_terms_optional_scheduling_receipt.sql` (fresh bootstrap successor)
  - `db/schema_parts/1045_order_terms_optional_scheduling_receipt.sql`
  - `db/migration_releases/labor_union_2026_09_22_order_terms_optional_scheduling_receipt_v1.json`
  - `db/migration_releases/labor_union_2026_09_22_order_terms_optional_scheduling_receipt_v1.descriptors.json`

- current zero client obligation establishment release:
  - `db/schema_parts/1046_client_zero_obligation_establishment.sql` — shared fresh-bootstrap／preserve-data CHECK successor; only established zero amounts with both due dates null may remain unchanged.
  - `db/migration_releases/labor_union_2026_09_29_client_zero_obligation_establishment_v1.json`
  - `db/migration_releases/labor_union_2026_09_29_client_zero_obligation_establishment_v1.descriptors.json`
  - `validation/receipts/PROV-ZERO-OBLIGATION-local-additive-qualification-20260929.json` — reusable synthetic-MySQL fresh／preserve qualification; machine-local source backup remains mandatory.

## Contracts

- Cancellation optional downstream receipt release：`db/schema_parts/1048_order_cancellation_optional_downstream.sql`、fresh successor `db/schema_parts/229_order_cancellation_optional_downstream.sql`、`db/migration_releases/labor_union_2026_09_29_order_cancellation_optional_downstream_v1.json` 及其 descriptors。
- 對應 schema-only nullability／predecessor／drift contract：`tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_order_cancellation_optional_downstream_schema.py`。
- Source read-only、candidate identity、release classification、backup／journal／resume及
  replacement boundary — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`

## Verification
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/test_nas_database_upgrade.py` — cold-backup identity/integrity, operational-source exclusion, helper network isolation and bounded configuration switching.

- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_line_group_invitation_url_schema.py` — additive 私有網址欄位、release／fresh／descriptor 一致與 drift 拒絕。
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_nas_registration_approval_schema.py` — canonical registry、四欄 descriptor、absent／exact／partial／drift。
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_candidate_weekly_information_schema.py` — exact predecessor／successor、順序／型別／nullability drift 與限定的 additive SQL effect。
- layout_status: `custom_current`
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_staff_union_number_schema.py`
- test_root: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/`
- integration_root: `tests/test_collect_local_additive_engine_evidence.py`
- integration_root: `tests/test_local_database_maintenance.py`
- integration_root: `tests/test_schema_assembly.py` — 既有 fresh assembly 版本與分類驗證，沿原測試入口保存；新增 migration contract 使用 canonical module root。
- integration_root: `tests/test_order_lifecycle_pending_status_constraint_schema.py`
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_registry_owner_mutations_schema.py`
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_order_service_hours_half_precision_schema.py`
- contract: `tests/domains/global/subsystems/migration/modules/preserved-database-upgrade/contract/test_historical_manual_beclass_origin_schema.py`

## Provenance
- Preserve-data upgrade is a Global Migration capability distinct from fresh reset —
  `architecture_declared` — `document/架構重整/01_規格基線/10_Global_保留資料Migration與Cutover_Subsystem.md`
- Current runner and launchers implement the bounded developer workflow — `source_observed` —
  `scripts/update_local_database.py`

## Change triggers
- Reconcile when source／candidate policy、ordered release classification、backup／journal／resume、
  replacement planning、launcher routing or canonical verification roots change.
