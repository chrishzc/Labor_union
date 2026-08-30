"""
File: reconcile_writer_inventory_v3_dispositions.py
Description: 將人工 owner 裁決套用至不可變 writer inventory 候選證據。
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence" / "writer_inventory_v3"
CANDIDATE = EVIDENCE / "writer_inventory_v3_candidate.findings.jsonl"
RECORDS = EVIDENCE / "writer_inventory_v3_disposition.records.jsonl"
MANIFEST = EVIDENCE / "writer_inventory_v3_disposition.manifest.json"
COMMIT_DISPOSITIONS = EVIDENCE.parent / "task97_repository_commit_dispositions_v1.json"
REVIEW_REFRESH_PATHS = frozenset(
    {"infrastructure/mysql/admin_capability_grant_repository.py"}
)

# Source-locked semantic reviews.  A future source edit or new symbol fails
# closed back to needs_decision instead of inheriting a path-wide disposition.
EXACT_SOURCE_REVIEWS: dict[
    str,
    tuple[str, frozenset[str], tuple[str, str, str, str]],
] = {
    "infrastructure/db/external_staff_completion_port.py": (
        "4326a6cb059958eab18136bcf7b25442e3218b834366468bce14d0f1b7faeb7d", frozenset({"MySqlExternalStaffCompletionPort._ensure_commitment"}),
        ("contract_signing", "Contract Signing precontract commitment persistence inside external-signing outer Unit of Work", "typed ExternalSigningWorkflow staff completion", "retain_canonical:source-locked exact commitment and day mutations are Contract Signing-owned and commit only at application boundary"),
    ),
    "infrastructure/mysql/hcm_workbook_import_repository.py": (
        "a66e4f5c9bc1165bbde0d0d3cd5dae3f7f8210b2f2e84ba8ba3213190096333e", frozenset({"HcmWorkbookImportRepository.claim", "HcmWorkbookImportRepository.save_receipt"}),
        ("case_import", "Case Import HCM workbook intake transaction", "HcmWorkbookImportService", "retain_canonical:source-locked exact command claim and intake receipt are part of the Case Import application transaction"),
    ),
    "infrastructure/mysql/subsidy_advance_recovery_repository.py": (
        "4bf899c02ca02162d2ce5c59dbf86ea88cab9286d2e9da5c8309fcf08d6bd3da", frozenset({"MySqlSubsidyAdvanceRecoveryRepository.save_recovery", "MySqlSubsidyAdvanceRecoveryRepository.record_anomaly"}),
        ("client_finance", "Client Finance subsidy advance recovery inside worker outer transaction", "typed SubsidyAdvanceRecoveryWorkflow", "retain_canonical:source-locked exact recovery and Client Finance owner-outbox mutations; repository never commits"),
    ),
    "subsystems/orders/order_lifecycle_control_commands.py": (
        "e1601a45c931dbc841b6980c37461bfb8986f7c6a2d6d953f25a5bb557caee64", frozenset({"apply_order_lifecycle_control_command"}),
        ("orders", "typed Orders lifecycle-control command inside caller-owned outer Unit of Work", "Orders reopen, actual-start, cancellation, and owner-outbox workflows", "retain_canonical:source-locked exact CAS state and lifecycle event symbols; helper never commits"),
    ),
    "infrastructure/mysql/line_notification_repository.py": (
        "03f66aa8a009840a528ac8283f89bb188b0b7404687d8fe936ff5d038d10fcd6",
        frozenset({"MySqlLineNotificationRepository._create_intent_if_absent", "MySqlLineNotificationRepository._record_decision", "MySqlLineNotificationRepository.cancel_service_day_log_reminders", "MySqlLineNotificationRepository.cancel_service_day_log_reminders_for_assignments", "MySqlLineNotificationRepository.lock_and_cancel_rule_intents", "MySqlLineNotificationRepository.mark_delivery_task_provider_accepted", "MySqlLineNotificationRepository.register_source_event"}),
        ("line_delivery", "LINE notification source, intent, decision, cancellation, and provider-accepted delivery state", "typed notification rule, Scheduling projection, LINE delivery, and reconciliation applications", "retain_canonical:source-locked exact LINE-owned delivery/source state; Scheduling retains Service Day completion ownership and repository never commits"),
    ),
    "subsystems/access/security_alert_outbox.py": (
        "6f7edff630a53544e86e7ee2535589f4bfbc30cc5eb6b8d6db3d391ac34904c8",
        frozenset({"_mark_failed", "consume_security_alert_outbox"}),
        ("access_control", "Access-owned security alert outbox delivery state", "central worker using an explicitly composed alert sink and bounded success and failure transactions", "retain_canonical:source-locked exact Access outbox state mutations; Access owns durable intent and delivery state without importing a concrete downstream subsystem"),
    ),
    "infrastructure/mysql/process_reminder_anomaly_source.py": (
        "bd957704fed37ed53057413fd38d7ba7f0f8562365ead2c02dffa21c5c65a580",
        frozenset({"_fetch"}),
        ("anomalies", "bounded read-only process-reminder owner-fact source", "legacy AnomalyApplication maintenance flow", "retain_restricted:source-locked _fetch callsites execute SELECT-only constants and own no persistence mutation or transaction; the enclosing legacy projector runtime cutover remains tracked separately"),
    ),
    "subsystems/case_import/hcm_resubmission_outbox_consumer.py": (
        "4673ad8e9aa881893802efe8942b746332ade6c6c8403f179c24ac12f3a99f39",
        frozenset({"_mark_failed", "_mark_published", "_record_failure", "consume_hcm_resubmission_outbox"}),
        ("case_import", "Case Import HCM correction owner-outbox acknowledgement and bounded retry", "central worker invoking the Case Import owner consumer", "retain_canonical:source-locked canonical review delivery acknowledgement now resides with Case Import, validates fresh review/version facts, and contains no legacy occurrence mutation"),
    ),
    "subsystems/government_subsidy/subsidy_advance_outbox_consumer.py": (
        "28ba0625bf62919df514948ec9e7642b0dad334dc9625eb83ab45c67f324b373",
        frozenset({"_mark_delivered", "_mark_failed", "consume_government_subsidy_advance_events"}),
        ("government_subsidy", "Government Subsidy owner-outbox delivery to typed Client Finance recovery", "central worker invokes the Government Subsidy owner consumer", "retain_canonical:source-locked exact owner-outbox delivery and retry mutations remain Government Subsidy-owned while Client Finance recovery is delegated through its typed workflow"),
    ),
    "scripts/update_local_database.py": (
        "4c07082ca0f44da5497028af630702308edbecc3e996fed459ac6a6824a3eac7",
        frozenset({"discard_incomplete_candidate", "recreate_database"}),
        ("global_migration", "guarded developer-local database replacement and rollback", "operator CLI update_local_database", "retain_restricted:source-locked validated local candidate/source database operations remain operator-only behind host, environment, confirmation, backup, resume, verify, receipt, and authority gates"),
    ),
    "scripts/migration_artifacts/2026_08_02/migrate_order_details_lifecycle_version_view.py": (
        "6c9036557a2081f5965877c77121747ee120bd81661aff26f199224f125bb0f8",
        frozenset({"_count", "run_migration"}),
        ("global_migration", "immutable historical Orders lifecycle-view migration artifact", "entry inventory only; no current runtime caller", "retain_restricted:source-locked immutable artifact is blocked pending canonical-runner absorption and retirement receipt; no production authority"),
    ),
    "scripts/reset_fake_database.py": (
        "ec0959447a6a1f0e47cbb4b792dcff6ee8c6a0f64a86fe647d2ec7fff5e4cc0a",
        frozenset({"rebuild_schema"}),
        ("validation", "guarded disposable database schema reset", "operator CLI restricted to explicit lu_test target", "retain_restricted:source-locked schema assembly remains disposable-test-only behind target, confirmation, plan, backup, identity, verify, replay, receipt, and authority gates"),
    ),
    "scripts/import_db_snapshot_fixture_v2.py": (
        "917fdffe172c92aba162175018b30868b53ed9517492e7d6c61627949babe3b9",
        frozenset({"import_fixture"}),
        ("validation", "guarded disposable database snapshot fixture import", "operator CLI restricted to explicit lu_test target and fixed table allowlist", "retain_restricted:source-locked fixture import remains disposable-test-only behind checksum, target, plan, backup, confirmation, identity, verify, replay, receipt, and authority gates"),
    ),
    "scripts/init_db.py": (
        "d003891c68280c1dc2073ce696a3a6f56b379a5f814f44a6ea858884b5255562",
        frozenset({"load_schema_paths"}),
        ("validation", "borrowed canonical schema assembly loader", "reset_fake_database guarded disposable runner; direct main retired", "retain_restricted:source-locked explicit schema-path loader grants no standalone production database authority"),
    ),
    "scripts/reconcile_fixture_order_dates_v2.py": (
        "161763f6d0f170f6c93548fae3fbd57cb512a67c4ab475544b1f01df95b9311d",
        frozenset({"reconcile"}),
        ("validation", "fixed validation-fixture Orders date reconciliation", "validation CLI for fixed 50-case fixture", "retain_restricted:source-locked fixture-only mutation remains validation tooling and grants no production authority"),
    ),
    "infrastructure/mysql/historical_baseline_contract_signing_owner_adapter.py": (
        "4790bc62348ed8fce2611755421afce3ee4bad984e16f74ede35b75bd82f05fb",
        frozenset({"MySqlHistoricalBaselineContractSigningOwnerAdapter._rows"}),
        ("contract_signing", "bounded historical baseline Contract Signing owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed owner-table reads use a borrowed connection and grant no mutation authority"),
    ),
    "infrastructure/mysql/historical_baseline_matching_owner_adapter.py": (
        "551022d75c6c9da4470b6fa533193d08e6105da1acca27b1a857de6e34e76d6e",
        frozenset({"_rows"}),
        ("scheduling", "bounded historical baseline Matching owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed Scheduling/Matching reads use a borrowed connection and grant no mutation authority"),
    ),
    "infrastructure/mysql/historical_baseline_orders_owner_adapter.py": (
        "eb295ada9fe00d2c361ddedf16bd42652fdbccf1bd3b92c89a63d13fc5f00514",
        frozenset({"_rows"}),
        ("orders", "bounded historical baseline Orders owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed Orders reads use a borrowed connection and grant no mutation authority"),
    ),
    "infrastructure/mysql/historical_baseline_staff_payables_owner_adapter.py": (
        "ba3c95286114ff326119acd51d2915f2bbdb2b0dff4098e0fd8ad70f518c7c85",
        frozenset({"MySqlHistoricalBaselineStaffPayablesOwnerAdapter._read_case"}),
        ("staff_payables", "bounded historical baseline Staff Payables owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed owner-table reads use a borrowed connection and grant no mutation authority"),
    ),
    "infrastructure/mysql/data_browser_query_repository.py": (
        "0a779627343558692412359372fe8682d376fa5d817046aa14e5f48ff0bb9404",
        frozenset({"DataBrowserQueryRepository.query_masked_page"}),
        ("access_control", "bounded masked Data Browser query over fixed source allowlist", "authenticated data-browser source query API", "retain_restricted:source-locked source, columns, search, ordering, and limits are fixed; no arbitrary table or mutation authority"),
    ),
    "subsystems/scheduling/matching_coordination_application.py": (
        "3d06adbe26b3e1a9948caaf555db9c7fff212bade2803dec7021c00b12a03820",
        frozenset({"MatchingCoordinationApplication.query"}),
        ("scheduling", "typed Matching Coordination application query", "matching coordination GET API", "retain_restricted:source-locked query delegates only to typed owner-fact ports and performs no mutation or commit"),
    ),
    "infrastructure/mysql/staff_retirement_repository.py": (
        "b7bab58e479ab4972c004ebb05bccaa5276ddf1c37d2a76ad1d81a710bd636d9",
        frozenset({"MySqlStaffRetirementRepository.claim_command", "MySqlStaffRetirementRepository.persist"}),
        ("staff_operations", "Staff lifecycle repository inside typed workflow outer Unit of Work", "Staff Retirement Query/Preview/Apply", "retain_canonical:source-locked exact command claim, lifecycle state/event, and receipt mutations; repository never commits"),
    ),
    "infrastructure/mysql/scheduling_holiday_query.py": (
        "8305ebf35938e5ab03b2668225c55861dc6076feb5e1e6848ea13d66093b2f2b",
        frozenset({"MySqlSchedulingHolidayQuery.save_receipt", "MySqlSchedulingHolidayQuery.upsert_holiday", "MySqlSchedulingHolidayQuery.delete_holiday"}),
        ("scheduling", "Scheduling holiday maintenance persistence inside application outer Unit of Work", "typed Holiday Maintenance Query/Preview/Apply", "retain_canonical:source-locked exact holiday and receipt mutations; query identity remains read-only restricted"),
    ),
    "infrastructure/mysql/matching_successor_persistence_adapter.py": (
        "530bf699d3b52ac8dd59efdefec61b08b4c0b4854283edf4c8e86021640b99bd",
        frozenset({"MatchingSuccessorPersistenceAdapter._insert"}),
        ("scheduling", "Scheduling matching successor persistence through Service-Before-Replacement outer Unit of Work", "typed ServiceBeforeReplacementWorkflow", "retain_canonical:source-locked exact Scheduling package lineage/event insert; adapter never commits or rolls back"),
    ),
    "subsystems/scheduling/matching_plan_workflow.py": (
        "b8ffaa7944946441cb40c91a00d4d5e45e781937fb07d259df6dd48ad5b6ba4c",
        frozenset({"_create_matching_plan_version_in_transaction"}),
        ("scheduling", "Scheduling matching plan creation inside application outer Unit of Work", "typed matching-plan create API and guarded contract-signing validation runner", "retain_canonical:source-locked exact matching plan and segment mutations; application owns commit and rollback"),
    ),
    "infrastructure/mysql/beclass_import_review_repository.py": (
        "4de64e86d23580824bd7a66e1a562fddd505a1c312a66e72594922e3fe99f0fb",
        frozenset({"MySqlBeClassImportReviewRepository.append_invalid_row", "MySqlBeClassImportReviewRepository.append_outbox", "MySqlBeClassImportReviewRepository.append_resolution_event", "MySqlBeClassImportReviewRepository.claim_command", "MySqlBeClassImportReviewRepository.load", "MySqlBeClassImportReviewRepository.save_receipt", "_review_row_id"}),
        ("case_import", "Case Import BeClass review repository inside row or review-application outer Unit of Work", "Client BeClass workbook import and typed BeClass Review Query/Preview/Apply", "retain_canonical:source-locked exact review root, immutable event, outbox, command claim, read, and receipt symbols; separate payload writer remains independently gated"),
    ),
    "infrastructure/mysql/hcm_resubmission_repository.py": (
        "5cd6a828b410c7d5ae6e811a5673a6e8fdad34cf63d77e9bcabc43b256d361e4",
        frozenset({"MySqlHcmResubmissionRepository.append_outbox", "MySqlHcmResubmissionRepository.save_receipt"}),
        ("case_import", "Case Import HCM resubmission evidence repository inside workflow outer Unit of Work", "typed HCM Resubmission Preview/Apply", "retain_canonical:source-locked exact Case Import correction outbox and receipt symbols; cross-owner root updates and legacy warning associations remain migration blockers"),
    ),
    "infrastructure/mysql/order_lifecycle_impact_writer.py": (
        "75053ba3e2db8d416b8ef3e32f1828c1f3a81ec6a3508bc7b35063baf79da033",
        frozenset({"_append_lifecycle_event", "_append_orders_outbox", "_insert_service_data_lock", "persist_order_lifecycle_projection"}),
        ("orders", "typed Orders lifecycle impact writer using caller-owned cursor", "Orders, Scheduling, and Contract workflows through typed Orders persistence command", "retain_canonical:source-locked exact Orders projection, lifecycle event, owner outbox, and service-data-lock symbols; writer never commits"),
    ),
    "infrastructure/mysql/client_finance_terms_writer.py": (
        "699ad27830a2ce345d2f416ef48dadffc2db761e27df3887c4bcbe82d518f5bd",
        frozenset({"_advance_account_version", "_append_obligation_event", "_append_outbox", "_insert_projection", "_update_projection"}),
        ("client_finance", "typed Client Finance terms impact writer using caller-owned cursor", "Orders, Scheduling, and Contract Signing workflows through typed Client Finance command", "retain_canonical:source-locked exact Client Finance version, obligation event/projection, and owner-outbox symbols; writer never commits"),
    ),
    "infrastructure/mysql/staff_leave_intake_repository.py": (
        "1b32488d70292e28933f44518b0262ff4e387f2a0c4f9362ef6319e0d6235bb4",
        frozenset({"MySqlStaffLeaveIntakeRepository.create", "MySqlStaffLeaveIntakeRepository.resolve", "MySqlStaffLeaveIntakeRepository.transition"}),
        ("scheduling", "Scheduling staff leave request aggregate repository inside application outer Unit of Work", "Staff Leave Intake application and typed Leave Substitution linked resolution", "retain_canonical:source-locked exact Scheduling leave aggregate, event, receipt, and resolution-link symbols; repository never commits"),
    ),
    "infrastructure/mysql/leave_substitution_repository.py": (
        "0305b5186158aef9a3dd7bcaeaa71a59e504c043fc0e209d25297af1ed135c8e",
        frozenset({"MySqlLeaveSubstitutionRepository.save_receipt", "_insert_batch_header", "_insert_claim", "_insert_leave_occupancy", "_insert_outcome"}),
        ("scheduling", "Scheduling leave substitution repository inside workflow outer Unit of Work", "typed Leave Substitution Preview/Apply", "retain_canonical:source-locked exact Scheduling batch, claim, occupancy, outcome, and receipt symbols; Payroll special-pay persistence is delegated through a typed borrowed-UoW port"),
    ),
    "subsystems/scheduling/availability_lock_acquisition_workflow.py": (
        "eebff3a7f5c629ba772c2d0c008706284c7f4e7caadbcfae7f72e8a42d0f16bf",
        frozenset({"_acquire_caregiver_availability_lock_in_transaction"}),
        ("scheduling", "Scheduling caregiver availability lock acquisition inside application outer Unit of Work", "typed availability-lock acquisition API", "retain_canonical:source-locked exact lock, day, event, and matching-plan invalidation mutations; application owns the transaction"),
    ),
    "subsystems/scheduling/availability_lock_cancellation_workflow.py": (
        "caedac8c2e3091d83905c38d1e7d21f3ac21d85e1ffd17cfc386c0c34923ab74",
        frozenset({"cancel_caregiver_availability_lock_for_order"}),
        ("scheduling", "typed Scheduling availability-lock cancellation inside Orders outer Unit of Work", "Order Cancellation workflow through explicit Scheduling delegate", "retain_canonical:source-locked exact lock, day, and event mutations use the caller-owned outer transaction and no nested commit"),
    ),
    "subsystems/scheduling/availability_lock_release_workflow.py": (
        "53f7817722523e7e81dae5e19feccdea21a0c00064f0996df5f3223c37edbf90",
        frozenset({"_release_caregiver_availability_lock_in_transaction"}),
        ("scheduling", "Scheduling caregiver availability lock release inside application outer Unit of Work", "typed availability-lock release API", "retain_canonical:source-locked exact lock, day, event, and matching-plan invalidation mutations; application owns the transaction"),
    ),
    "subsystems/scheduling/matching_communication_workflow.py": (
        "f0a613ad24164b7bc3614d54511107a8dc07bf008fa46aa948c9aff6da9a7b0f",
        frozenset({"_cancel_matching_plan_in_transaction", "_record_matching_plan_willingness_in_transaction"}),
        ("scheduling", "Scheduling matching communication mutation inside application outer Unit of Work", "matching cancellation API and typed LINE willingness handler", "retain_canonical:source-locked exact active plan cancellation and willingness event symbols; delivery uses the replacement notification application"),
    ),
    "infrastructure/mysql/import_warning_auto_resolution.py": (
        "17f6f54d133d97b7670ae217e08e33c9034db415519453ff8faf67fb2ef18496",
        frozenset({"_append_auto_resolved_event"}),
        ("case_onboarding", "Case Onboarding import-warning auto-resolution inside consumer-owned transaction", "HCM resubmission outbox consumer", "retain_canonical:source-locked exact current warning task, transition, outbox, and receipt mutations; this is Case Onboarding review state, not Anomalies occurrence history"),
    ),
    "infrastructure/mysql/import_warning_tracking_repository.py": (
        "406887d9898984e91acb1ab13fd1338cadf9ec09e6aa4b71d252d24e18a0f388",
        frozenset({"MySqlImportWarningTrackingRepository.apply_transition"}),
        ("case_onboarding", "Case Onboarding import-warning tracking repository inside application outer Unit of Work", "typed Import Warning Tracking Query/Preview/Apply", "retain_canonical:source-locked exact current warning task, transition, outbox, and receipt mutations; repository never commits"),
    ),
    "subsystems/finance_import/staging.py": (
        "75037bd6b306af580b7401dfeb72072de7b76ddffc381a2fa1195f20bfc70e4a",
        frozenset({"stage_finance_rows"}),
        ("finance_import", "Finance Import staging inside ingestion-owned outer transaction", "ingest_finance_workbook via _ingest_or_replay", "retain_canonical:source-locked exact batch, occurrence, and row staging symbols; diagnostic caller rolls back and grants no independent mutation authority"),
    ),
    "subsystems/finance_import/finance_import_anomaly_consumer.py": (
        "acd90bcc56e8184bc2546f7fe03c5dc4d6f5e6dfa653ea78359291c9d369325d",
        frozenset({"_consume_next", "_mark_delivered", "_mark_failed", "_record_failure"}),
        ("finance_import", "Finance Import owner-outbox acknowledgement, bounded retry, and typed IMPORT-006 dispatch", "central worker invoking the Finance Import owner consumer with an explicit runtime port", "retain_canonical:source-locked owner outbox and source-review acknowledgement now reside with Finance Import and contain no legacy warning occurrence, tracking, or current-task mutation"),
    ),
    "subsystems/case_import/beclass_import_outbox_consumer.py": (
        "ea168b07496531dfac535757ad6beb8682471a2d5ec44ca1f8fd41f3473ba36f",
        frozenset({"_consume_next", "_mark_delivered", "_mark_failed", "_record_failure"}),
        ("case_import", "Case Import BeClass canonical-review owner-outbox acknowledgement and bounded retry", "central worker invoking the Case Import owner consumer", "retain_canonical:source-locked owner outbox acknowledgement validates the canonical review root and resolution event and contains no legacy warning occurrence or current-task mutation"),
    ),
    "subsystems/orders/historical_order_adoption_outbox_consumer.py": (
        "172731265ecb70bc652d584f6d33e2f953f3e297afaae2bb51ad09c34d63a694",
        frozenset({"_consume_next", "_mark_delivered", "_mark_failed", "_record_failure"}),
        ("orders", "Orders historical-adoption owner-outbox acknowledgement and bounded retry", "central worker invoking the Orders owner consumer", "retain_canonical:source-locked consumer validates Orders review and receipt facts, acknowledges the owner outbox, and contains no legacy warning occurrence or Anomaly projection mutation"),
    ),
    "subsystems/orders/historical_order_review_remediation_outbox_consumer.py": (
        "f608c569f2a29efe59647b9aa7fa21f1f248bc9206366bc5cae04312507c4888",
        frozenset({"_consume_next", "_mark_delivered", "_mark_failed", "_record_failure"}),
        ("orders", "Orders historical-review remediation owner-outbox acknowledgement and bounded retry", "central worker invoking the Orders owner consumer", "retain_canonical:source-locked consumer validates fresh Orders root, disposition, review, and receipt facts and contains no legacy warning close/history or Anomaly projection mutation"),
    ),
    "infrastructure/mysql/historical_order_review_remediation_repository.py": (
        "37a74363064dbcc23a7b2dd124df9c0193f917abc66bf61bd3c42b5cc1cb96cc",
        frozenset({"MySqlHistoricalOrderReviewRemediationRepository.persist"}),
        ("orders", "historical Orders review-remediation repository inside workflow outer Unit of Work", "typed historical Orders remediation Query/Preview/Apply", "retain_canonical:source-locked exact Orders-owned remediation event, outbox, and receipt symbols; this grants no Anomalies occurrence/history authority"),
    ),
    "infrastructure/mysql/matching_coordination_repository.py": (
        "5468d3ce405340ef15b8f47f11b96e546ec4578a78c94b213b403e7e69771f55",
        frozenset({"MySqlMatchingCoordinationRepository._ensure_event", "MySqlMatchingCoordinationRepository._ensure_package", "MySqlMatchingCoordinationRepository._ensure_snapshot", "MySqlMatchingCoordinationRepository.append_typed_intents", "MySqlMatchingCoordinationRepository.save_receipt"}),
        ("scheduling", "Scheduling Matching Coordination repository inside application outer Unit of Work", "typed Matching Coordination Query/Preview/Apply and Service-Before-Replacement composition", "retain_canonical:source-locked exact immutable snapshot, package, event, receipt, and owner-intent symbols; repository never commits"),
    ),
    "infrastructure/mysql/customer_service_escalation_repository.py": (
        "13e2536420ae383c9bde29fc9fa7fcee096616e1c406e1fadfc4099db9cb00ba",
        frozenset({"MySqlCustomerServiceEscalationRepository.append_event", "MySqlCustomerServiceEscalationRepository.append_source_event", "MySqlCustomerServiceEscalationRepository.create", "MySqlCustomerServiceEscalationRepository.enqueue_masked_alert", "MySqlCustomerServiceEscalationRepository.save_receipt", "MySqlCustomerServiceEscalationRepository.transition"}),
        ("customer_service", "Customer Service escalation repository inside workflow outer Unit of Work", "typed Customer Service escalation Query/Preview/Apply", "retain_canonical:source-locked exact escalation, source-event, masked-alert enqueue, transition, and receipt symbols; repository never commits"),
    ),
    "infrastructure/db/contract_external_signing_repository.py": (
        "715def0bda249e10b685782ecf2ca846b926582520ffd08ccb83c15c03c4ddc1",
        frozenset({"MySqlContractExternalSigningRepository._insert", "MySqlContractExternalSigningRepository.advance_session", "MySqlContractExternalSigningRepository.complete_session_and_recovery"}),
        ("contract_signing", "Contract Signing external-session repository inside application outer Unit of Work", "typed Contract External Signing and recovery workflows", "retain_canonical:source-locked exact signing-session and recovery-task mutation symbols; repository never commits and provider effects remain outside the transaction"),
    ),
    "infrastructure/db/contract_unsigned_pdf_repository.py": (
        "2227bb7cc251ac9f24e82df2c25382c7b121f8a5a86c2ae9d317e66e3361ffda",
        frozenset({"MySqlContractUnsignedPdfRepository._execute", "MySqlContractUnsignedPdfRepository._insert"}),
        ("contract_signing", "Contract Signing unsigned-PDF repository inside application outer Unit of Work", "typed unsigned-PDF generation and persistence workflow", "retain_canonical:source-locked exact unsigned-PDF mutation symbols; repository never commits"),
    ),
    "infrastructure/mysql/staff_availability_repository.py": (
        "adb4eb016e43b816ef8adf362c51977f11458478e81fe6ed774710a0bb509437",
        frozenset({"MySqlStaffAvailabilityRepository.append_event", "MySqlStaffAvailabilityRepository.cancel_block", "MySqlStaffAvailabilityRepository.create_block", "MySqlStaffAvailabilityRepository.end_pause", "MySqlStaffAvailabilityRepository.increment_version", "MySqlStaffAvailabilityRepository.load_matching_facts", "MySqlStaffAvailabilityRepository.save_receipt", "_load_block", "_load_version", "_occupancy_conflicts", "_overlapping_blocks", "_require_block", "_require_staff"}),
        ("scheduling", "Scheduling staff availability repository inside workflow outer Unit of Work or typed read port", "Staff Availability Query/Preview/Apply and typed Matching or Service-Before-Replacement callers", "retain_canonical:source-locked exact availability aggregate, block, event, receipt, and bounded fact-read symbols; repository never commits"),
    ),
    "infrastructure/mysql/staff_matching_preference_repository.py": (
        "eeb1b077e25e27dd664083086f89557bc32877d818ec8c7861778779e6f1c272",
        frozenset({"MySqlStaffMatchingPreferenceRepository.append_event", "MySqlStaffMatchingPreferenceRepository.find_receipt", "MySqlStaffMatchingPreferenceRepository.list_definitions", "MySqlStaffMatchingPreferenceRepository.load_definition", "MySqlStaffMatchingPreferenceRepository.load_profile", "MySqlStaffMatchingPreferenceRepository.save_definition", "MySqlStaffMatchingPreferenceRepository.save_profile", "MySqlStaffMatchingPreferenceRepository.save_receipt", "_delete_removed_values"}),
        ("scheduling", "Scheduling staff matching preference repository inside workflow outer Unit of Work or typed read port", "Staff Matching Preference Query/Preview/Apply and typed Matching or Service-Before-Replacement callers", "retain_canonical:source-locked exact preference definition, profile, event, receipt, and bounded read symbols; repository never commits"),
    ),
    "subsystems/scheduling/candidate_contact_pool_workflow.py": (
        "3dce2da56ef343b11d3b6def6dde5c5e9cdeecd5fdbafc038c0071ee214642f3",
        frozenset({"_add_candidates_in_transaction", "_apply_manual_information_confirmation_in_transaction", "_record_willingness_in_transaction", "_run_in_application_uow", "_send_information_in_transaction", "query_pool"}),
        ("scheduling", "Scheduling candidate contact pool application transaction and bounded query", "candidate contact pool API and typed Matching Coordination read", "retain_canonical:source-locked exact pool, entry, event, committed LINE-task enqueue, and bounded query symbols; external delivery remains outside the transaction"),
    ),
    "infrastructure/mysql/service_date_confirmation_repository.py": (
        "37d3bd8fa01f41b81ec4ede1be8bde5e00476e0f763650f8bedbbd319a64895c",
        frozenset({"MySqlServiceDateConfirmationRepository._dates", "MySqlServiceDateConfirmationRepository._suggested_dates", "MySqlServiceDateConfirmationRepository.load"}),
        ("orders", "Orders Confirmed Service Dates bounded repository read", "Service Date Confirmation Query/Preview/Apply and typed Scheduling consumers", "retain_canonical:source-locked exact Orders-owned confirmed-date reads; no Scheduling writer authority is granted"),
    ),
    "subsystems/anomalies/system_alert_projection.py": (
        "e325203fa1db10e33906ae00c5e16668d5487d6ff982ea977a9f15bc2b7de2dd",
        frozenset({"upsert_system_alert"}),
        ("anomalies", "Anomalies-owned system_alerts projection inside a caller-owned delivery Unit of Work", "central architecture worker composition through an explicit Access alert-sink port", "retain_restricted:source-locked Anomalies projection issues SQL without commit ownership; Access durable intent and delivery state remain Access-owned"),
    ),
    "infrastructure/mysql/order_actual_start_repository.py": (
        "b634cf8a4f1ee42b4cdd78485393a898801b193b1e2e12c82bdadaccf79f352c",
        frozenset({"MySqlOrderActualStartRepository.append_actual_start_event", "MySqlOrderActualStartRepository.find_actual_start_receipt", "MySqlOrderActualStartRepository.save_actual_start_receipt", "MySqlOrderActualStartRepository.update_actual_start", "_insert_claim", "_select_actual_start_control", "_select_deposit_settlement_projection"}),
        ("orders", "Orders Actual Start repository inside workflow outer Unit of Work", "typed Order Actual Start Query/Preview/Apply", "retain_canonical:source-locked exact claim, fact read, lifecycle, order update, and receipt symbols; repository never commits"),
    ),
    "infrastructure/mysql/order_cancellation_repository.py": (
        "c6312df8be3f74bcd203711ec29a3cf1ecbe4097894f002f8abbe9ee28822235",
        frozenset({"MySqlOrderCancellationRepository.append_cancellation_event", "MySqlOrderCancellationRepository.find_receipt", "MySqlOrderCancellationRepository.save_receipt", "MySqlOrderCancellationRepository.update_cancelled_order", "_append_lifecycle_outbox", "_insert_claim", "_insert_lifecycle_event"}),
        ("orders", "Orders cancellation repository inside workflow outer Unit of Work", "typed Order Cancellation Query/Preview/Apply", "retain_canonical:source-locked exact claim, lifecycle, outbox, order update, and receipt symbols; cross-domain effects remain typed and caller-owned"),
    ),
    "infrastructure/mysql/order_auto_completion_repository.py": (
        "30e57e7d062507299abc92ad5b452fe8e87c21c4bc54a33e486aecb58147808b",
        frozenset({"MySqlOrderAutoCompletionRepository.append_lifecycle_event", "MySqlOrderAutoCompletionRepository.append_outbox", "MySqlOrderAutoCompletionRepository.save_receipt", "MySqlOrderAutoCompletionRepository.update_order", "_insert_claim"}),
        ("orders", "Orders auto-completion repository inside service outer Unit of Work", "typed AutoCompleteOrderService Preview/Apply and durable-job composition", "retain_canonical:source-locked exact claim, lifecycle, order update, outbox, and receipt symbols"),
    ),
    "infrastructure/mysql/order_terms_repository.py": (
        "d6202cf7290e018b1ec88f0c735aab6c8394f0d2a73ba99196d59ac698da1106",
        frozenset({"MySqlOrderTermsRepository.append_terms_event", "MySqlOrderTermsRepository.find_receipt", "MySqlOrderTermsRepository.save_receipt", "MySqlOrderTermsRepository.update_order_terms", "_insert_command_claim"}),
        ("orders", "Orders terms repository inside workflow outer Unit of Work", "typed Order Terms Query/Preview/Apply", "retain_canonical:source-locked exact claim, terms event, Orders update, and receipt symbols; cross-domain effects remain typed and caller-owned"),
    ),
    "infrastructure/mysql/scheduling_replacement_writer.py": (
        "d25f278a93b79fa82e746c447954cb9b5915de9d0a0026aa529e33214982842f",
        frozenset({"_activate_new_generation", "_advance_aggregate", "_append_lineage", "_append_notification_invalidation_outbox", "_append_rebuild_event", "_cancel_previous", "_cancel_previous_assignments", "_cancel_previous_buffers", "_cancel_previous_leave_occupancy", "_cancel_previous_schedules", "_insert_active_buffer", "_insert_assignments", "_insert_generation", "_insert_occupancy", "_insert_released_buffer", "_insert_schedules", "_insert_scheduling_receipt"}),
        ("scheduling", "Scheduling replacement generation writer inside caller-owned outer Unit of Work", "Assignment Plan, Leave Substitution, and typed Orders workflows", "retain_canonical:source-locked exact Scheduling generation, lineage, receipt, and notification-invalidation symbols; writer never commits"),
    ),
    "infrastructure/mysql/service_before_replacement_repository.py": (
        "be730a683e889c808df1b0751a12dbd4301e01a6c72a8a1a2233771ea07d1c86",
        frozenset({"MySqlServiceBeforeReplacementRepository._cancel_r03_waiting_lock", "MySqlServiceBeforeReplacementRepository._insert_event", "MySqlServiceBeforeReplacementRepository._insert_outbox", "MySqlServiceBeforeReplacementRepository._insert_receipt", "MySqlServiceBeforeReplacementRepository._insert_roots", "MySqlServiceBeforeReplacementRepository._insert_successor", "MySqlServiceBeforeReplacementRepository._read_root_sets", "MySqlServiceBeforeReplacementRepository._require_r03_waiting_lock_readback", "MySqlServiceBeforeReplacementRepository.create_replacement_generation", "MySqlServiceBeforeReplacementRepository.find_receipt", "MySqlServiceBeforeReplacementRepository.load_owner_readback"}),
        ("scheduling", "Service Before Replacement repository inside workflow outer Unit of Work", "api/dependencies/service_before_replacement.py via ServiceBeforeReplacementWorkflow.apply", "retain_canonical:source-locked exact root, successor, generation, receipt, outbox, and bounded readback symbols; repository never commits"),
    ),
    "infrastructure/mysql/matching_schedule_confirmation_repository.py": (
        "fa1cd5b466ba19a9f1baa9c1bb4d939162b62734bbc5a34f14c2def0ae7412c7",
        frozenset({"MySqlMatchingScheduleConfirmationRepository._enqueue", "MySqlMatchingScheduleConfirmationRepository._manual_source", "MySqlMatchingScheduleConfirmationRepository._request_line_rejection_reason", "MySqlMatchingScheduleConfirmationRepository._store_recipient", "MySqlMatchingScheduleConfirmationRepository.confirm", "MySqlMatchingScheduleConfirmationRepository.confirm_line_postback", "MySqlMatchingScheduleConfirmationRepository.confirm_line_rejection_reason", "MySqlMatchingScheduleConfirmationRepository.invalidate_current_snapshot", "MySqlMatchingScheduleConfirmationRepository.prepare_manual", "MySqlMatchingScheduleConfirmationRepository.send"}),
        ("scheduling", "Matching Schedule confirmation repository inside API or LINE application Unit of Work", "typed confirmation API and LineMatchingPostbackApplication", "retain_canonical:source-locked exact snapshot, confirmation, recipient, interaction, and bounded read-lock symbols; repository never commits"),
    ),
    "infrastructure/db/controlled_file_repository.py": (
        "adac676918a117074f5d4fdb8683a69bf770ec3b16d0ec904efeac709a0b3e7b",
        frozenset({"MySqlControlledFileWorkflowRepository.append_reconciliation_event", "MySqlControlledFileWorkflowRepository.begin_cleanup", "MySqlControlledFileWorkflowRepository.claim_command", "MySqlControlledFileWorkflowRepository.complete_cleanup", "MySqlControlledFileWorkflowRepository.fail_cleanup", "MySqlControlledFileWorkflowRepository.mark_staging_registered", "MySqlControlledFileWorkflowRepository.register_file", "MySqlControlledFileWorkflowRepository.register_staging", "MySqlControlledFileWorkflowRepository.save_receipt"}),
        ("controlled_files", "Controlled Files workflow, cleanup, or reconciliation outer Unit of Work", "ControlledFileWorkflow, ControlledFileCleanupWorkflow, and ControlledFileReconciler", "retain_canonical:source-locked exact staging, file, cleanup, receipt, and reconciliation mutations use caller-owned UoWs"),
    ),
    "infrastructure/mysql/client_deposit_reversal_repository.py": (
        "ab46f559639c4f241d0fc82dd917ba3a2028d0ab3f8e1c85442522a114bbfee4",
        frozenset({"MySqlClientDepositReversalRepository._append_outbox", "MySqlClientDepositReversalRepository.append_reversal_ledger_entry", "MySqlClientDepositReversalRepository.reopen_deposit_obligation", "MySqlClientDepositReversalRepository.replace_deposit_settlement", "MySqlClientDepositReversalRepository.save_receipt"}),
        ("client_finance", "Client Finance deposit reversal repository inside DepositReversalWorkflow outer Unit of Work", "typed Client Finance deposit reversal Preview/Apply", "retain_canonical:source-locked exact ledger, obligation, settlement, account, receipt, and outbox mutations; repository never commits"),
    ),
    "infrastructure/mysql/order_reopen_repository.py": (
        "8760255c82ed253c8b4c7fef0e9ad2a9258c6d489bf5a782c0ae0127a2997b7c",
        frozenset(
            {
                "MySqlOrderReopenRepository.append_reopen_event",
                "MySqlOrderReopenRepository.find_receipt",
                "MySqlOrderReopenRepository.save_receipt",
                "MySqlOrderReopenRepository.update_reopened_order",
                "_actual_start_reconfirmed",
                "_append_lifecycle_outbox",
                "_client_financial_rows",
                "_insert_claim",
                "_insert_lifecycle_event",
                "_load_account_versions",
                "_load_active_cancellation",
                "_load_order_row",
                "_staff_financial_rows",
            }
        ),
        (
            "orders",
            "Orders reopen repository inside OrderReopenWorkflow outer Unit of Work",
            "api/routes/order_reopen.py via api/dependencies/order_reopen.py",
            "retain_canonical:source-locked exact symbols are covered by typed reopen Preview/Apply, replay, stale, lifecycle, and rollback tests",
        ),
    ),
    "infrastructure/mysql/historical_order_adoption_repository.py": (
        "f23f399da1c453e72214d16e7e9bdff088e3fcba738117fc4d84634d16479a74",
        frozenset(
            {
                "MySqlHistoricalOrderAdoptionRepository._append_pairing_evidence",
                "MySqlHistoricalOrderAdoptionRepository._append_receipt",
                "MySqlHistoricalOrderAdoptionRepository._append_review",
                "MySqlHistoricalOrderAdoptionRepository._apply_order",
                "MySqlHistoricalOrderAdoptionRepository.active_assignments",
                "MySqlHistoricalOrderAdoptionRepository.load_order",
                "MySqlHistoricalOrderAdoptionRepository.resolve_staff",
                "_insert_outbox",
            }
        ),
        (
            "orders",
            "restricted historical Orders adoption row transaction",
            "historical_order_adoption API via HistoricalOrderWorkbookImportService and HistoricalOrderAdoptionWorkflow",
            "retain_restricted:source-locked historical review, Orders root adoption, receipt, and outbox symbols remain archive-required and may not become a daily import path",
        ),
    ),
    "infrastructure/mysql/historical_assignment_writer.py": (
        "767c303241449ab7695886f33ceebdcb873f470ebe18b678bc81fee5ee7fc000",
        frozenset({"MySqlHistoricalAssignmentWriter.append_completed_assignments"}),
        (
            "scheduling",
            "typed Scheduling historical assignment persistence using the caller-owned connection",
            "HistoricalOrderAdoptionWorkflow through SchedulingHistoricalAssignmentPort",
            "retain_canonical:source-locked exact completed-assignment insert is Scheduling-owned and the writer never commits or rolls back",
        ),
    ),
    "infrastructure/mysql/case_architecture_bootstrap_repository.py": (
        "089b609e6945b7f17113695f2225f3a650d3396e7d8505b44b5c715d2a54190e",
        frozenset(
            {
                "MySqlCaseArchitectureBootstrapRepository.claim_command",
                "MySqlCaseArchitectureBootstrapRepository.find_receipt",
                "MySqlCaseArchitectureBootstrapRepository.save_receipt",
                "_insert_accounts",
                "_insert_bootstrap_event",
                "_insert_client_payment_terms",
                "_insert_current_client_payment_terms",
                "_insert_payroll_policy_snapshot",
                "_select_optional_row",
                "_select_order",
                "_select_rate_policy",
                "_select_root_event",
            }
        ),
        (
            "case_import",
            "Case Import architecture bootstrap repository inside one bootstrap or Case Import outer Unit of Work",
            "case_architecture_bootstrap API and CaseImportWorkflow._apply_fresh",
            "retain_canonical:source-locked exact bootstrap symbols are the single reviewed cross-domain bootstrap adapter; no generic cross-domain writer authority is granted",
        ),
    ),
    "infrastructure/mysql/finance_import_repository.py": (
        "d7d174528580740b86654543ec415d0d322fb2cb3a1155129e69a0df742b2432",
        frozenset(
            {
                "MySqlFinanceImportRepository._insert_outbox",
                "MySqlFinanceImportRepository.advance_batch_version",
                "MySqlFinanceImportRepository.append_dispatch_audit",
                "MySqlFinanceImportRepository.append_manual_classification",
                "MySqlFinanceImportRepository.append_reconciliation_receipt",
                "MySqlFinanceImportRepository.load_refund_return_review",
                "MySqlFinanceImportRepository.save_correction_receipt",
                "MySqlFinanceImportRepository.save_receipt",
            }
        ),
        (
            "finance_import",
            "typed Finance Import repository inside caller-owned application Unit of Work",
            "api/dependencies/finance_import.py and api/dependencies/durable_job_handlers.py",
            "retain_canonical:exact source and symbols are covered by Finance Import Preview/Apply, replay, rollback, correction, review, and durable-handler tests",
        ),
    ),
    "scripts/migrate_assignment_schedule_integrity.py": (
        "e31469da149c9567ad028f883c161f58084377b8db1ff7f845439b31d15f8595",
        frozenset({"get_indexes_info", "inspect_duplicate_dates", "inspect_ownership_conflicts"}),
        ("global_migration", "read-only Scheduling integrity inspection", "operator CLI review entry", "retain_restricted:source-locked SELECT-only migration inspection; apply and production authority remain fail-closed"),
    ),
    "scripts/migrate_order_details_lifecycle_version_view.py": (
        "3d17f71bf1e8d3f50f214fcd7aea6d2346ccd96eaf4b5af204b2db62efdce61e",
        frozenset({"_count", "run_migration"}),
        ("global_migration", "Orders lifecycle library migration", "migrate_preserved_database_additive_schema.py::run_candidate_post_schema", "retain_restricted:source-locked library-only view migration is absorbed by the canonical runner and grants no standalone executable authority"),
    ),
    "scripts/migrate_order_lifecycle_control_facts.py": (
        "1dd816bebe7a1b538ee10d1b6f2ba247d2b8ccb59a36be9735276d6f193c082e",
        frozenset({"_insert_bootstrap", "_load_orders"}),
        ("global_migration", "Orders lifecycle control-fact backfill", "migrate_preserved_database_additive_schema.py preserve-data runner", "retain_restricted:immutable source-locked migration remains guarded; no production apply or hash change authorized"),
    ),
    "scripts/migrate_preserved_database_additive_schema.py": (
        "ab69ed0fa637b387fa7f3b3e34fa3fc3375d2393da9bf06f9fcac0d599a79c79",
        frozenset({"_rebuild_empty_legacy_knowledge_candidate", "apply_schema", "local_additive_apply", "restore_candidate"}),
        ("global_migration", "canonical preserve-data migration orchestrator", "authorized release or maintenance operator", "retain_restricted:source-locked operator runner remains subject to target, plan, backup, verify, replay, receipt, and authority gates"),
    ),
    "scripts/migrate_scheduling_generation_bootstrap.py": (
        "89fc8a927c4f2e6cd1695c9437aafd21cde3957f0efd0549ac089e79d4576cca",
        frozenset({"_load_assignments", "_load_orders", "_load_schedules"}),
        ("global_migration", "Scheduling generation bootstrap inspection helpers", "operator CLI review entry", "retain_restricted:immutable source-locked SELECT helpers; apply and production authority remain guarded"),
    ),
}

EXACT_SOURCE_RESTRICTED_REVIEWS: dict[
    str,
    tuple[str, frozenset[str], tuple[str, str, str, str]],
] = {
    "infrastructure/mysql/historical_order_workbook_import_repository.py": (
        "094ea14320c739c6c00b471016187790b030e1007d22938e7341a6e4aa0a32be", frozenset({"HistoricalOrderWorkbookImportRepository.claim", "HistoricalOrderWorkbookImportRepository.save_receipt"}),
        ("orders", "restricted historical Orders workbook adoption intake", "HistoricalOrderWorkbookImportService", "retain_restricted:source-locked claim and admin receipt remain historical-only and may not become a daily import path"),
    ),
    "infrastructure/mysql/finance_import_owning_domain_composite.py": (
        "5203191464aef0ae5a2fbcf5ce3ff10c7c707822e462e763ebaeb744a76a60b0", frozenset({"_resolve_client_receipt"}),
        ("finance_import", "bounded Finance Import owning-domain receipt resolution query", "FinanceImportWorkflow Preview/Apply", "retain_restricted:source-locked fixed Client Finance and optional Orders reads grant no independent writer authority"),
    ),
    "infrastructure/mysql/order_cancellation_read_model.py": (
        "6a7da4d7a4961cac4688f044a7711ce4ee154a9863f73610541a978b94ebac23", frozenset({"_load_cancellation_assignments"}),
        ("orders", "bounded Orders cancellation assignment fact read", "typed Order Cancellation Preview/Apply", "retain_restricted:source-locked fixed Scheduling projection read plus optional lock grants no cross-owner mutation authority"),
    ),
    "subsystems/finance_import/application.py": (
        "5a6ddccf82d8c940d869806c7df215dd598b4e07275d1e2c1b659eab000831a0", frozenset({"_complete_diagnostic_dry_run"}),
        ("finance_import", "rollback-only Finance Import diagnostic dry-run mutation", "diagnostic import_finance_workbook path", "retain_restricted:source-locked diagnostic update is always rolled back and grants no canonical ingestion authority"),
    ),
    "infrastructure/mysql/line_notification_repository.py": (
        "03f66aa8a009840a528ac8283f89bb188b0b7404687d8fe936ff5d038d10fcd6",
        frozenset({"MySqlLineNotificationRepository.list_sources_without_decisions"}),
        ("line_delivery", "bounded LINE notification source-without-decision query", "notification reconciliation application", "retain_restricted:source-locked fixed query grants no independent writer authority"),
    ),
    "infrastructure/mysql/line_media_asset_query_repository.py": (
        "f24db4a77ab09a27b42f56134bfcce6c7e9ec8ea603c954a67010ad8887aa2cd",
        frozenset({"MySqlLineRichMenuMediaAssetQueryRepository._get"}),
        ("line_integration", "bounded LINE media asset read and optional validation lock", "LINE media query and configuration Apply", "retain_restricted:source-locked typed owner-scoped media read grants no mutation authority"),
    ),
    "infrastructure/mysql/staff_retirement_repository.py": (
        "b7bab58e479ab4972c004ebb05bccaa5276ddf1c37d2a76ad1d81a710bd636d9",
        frozenset({"MySqlStaffRetirementRepository.load"}),
        ("staff_operations", "bounded Staff lifecycle fact read and lock", "Staff Retirement Query/Preview/Apply and typed Scheduling consumers", "retain_restricted:source-locked fixed lifecycle reads grant no independent writer authority"),
    ),
    "infrastructure/mysql/historical_baseline_scheduling_owner_adapter.py": (
        "4cadd592bc1196b50366a4cda228e8422bfdea4dff4f7c7242a932466ba856fd",
        frozenset({"MySqlHistoricalBaselineSchedulingOwnerAdapter._confirmed_dates", "MySqlHistoricalBaselineSchedulingOwnerAdapter._effective_generation", "MySqlHistoricalBaselineSchedulingOwnerAdapter._official_rows"}),
        ("scheduling", "bounded historical baseline Scheduling owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed owner-table reads use a borrowed connection and grant no mutation authority"),
    ),
    "infrastructure/mysql/scheduling_holiday_query.py": (
        "8305ebf35938e5ab03b2668225c55861dc6076feb5e1e6848ea13d66093b2f2b",
        frozenset({"MySqlSchedulingHolidayQuery.query"}),
        ("scheduling", "bounded Scheduling holiday calendar read", "Holiday Maintenance, Leave Substitution, and holiday API", "retain_restricted:source-locked fixed holiday query grants no independent writer authority"),
    ),
    "infrastructure/mysql/scheduling_rebuild_notification_invalidation_repository.py": (
        "399f2c8d4e827cd3e824280f000a04160af2aba50ea0437d53d1acb76ac842e8",
        frozenset({"MySqlSchedulingRebuildNotificationInvalidationRepository.claim_due", "MySqlSchedulingRebuildNotificationInvalidationRepository.mark_published", "MySqlSchedulingRebuildNotificationInvalidationRepository.mark_retry_or_failed"}),
        ("scheduling", "restricted Scheduling rebuild notification-outbox delivery lifecycle", "LINE worker invalidation publisher", "retain_restricted:source-locked claim/publish/retry worker identities are bounded delivery state, not an interactive canonical mutation path"),
    ),
    "infrastructure/mysql/matching_successor_persistence_adapter.py": (
        "530bf699d3b52ac8dd59efdefec61b08b4c0b4854283edf4c8e86021640b99bd",
        frozenset({"MatchingSuccessorPersistenceAdapter._one"}),
        ("scheduling", "bounded Scheduling matching successor read and lock", "typed ServiceBeforeReplacementWorkflow", "retain_restricted:source-locked fixed read grants no independent writer authority"),
    ),
    "infrastructure/mysql/staff_historical_workbook_repository.py": (
        "00c209ec6ee421e12e6c61c158023cf2aef84b8704ce0b1bf204054974c71f15",
        frozenset({"MySqlStaffHistoricalWorkbookRepository.claim", "MySqlStaffHistoricalWorkbookRepository.save_receipt"}),
        ("case_import", "restricted staff historical workbook intake", "authenticated StaffHistoricalWorkbookService", "retain_restricted:source-locked command claim and admin receipt remain controlled historical import and may not become a daily writer"),
    ),
    "infrastructure/mysql/staff_qualification_master_repository.py": (
        "7daf145b45aec2d03aed860a673655d516de40dcb4e24719d2cf7befdcae5057",
        frozenset({"_load_relation", "_load_values"}),
        ("staff_operations", "bounded Staff qualification master read model", "StaffQualificationMasterQueryService", "retain_restricted:source-locked fixed SELECT helpers grant no mutation authority"),
    ),
    "infrastructure/mysql/scheduling_eligibility_collision_repository.py": (
        "a667800118fa15583d9088da0a26761b821752eae5aa7fa4eddc0fb6f9d7f98c",
        frozenset({"MySqlSchedulingEligibilityCollisionRepository._load_staff"}),
        ("scheduling", "bounded Scheduling eligibility collision query", "SchedulingEligibilityCollisionQueryWorkflow", "retain_restricted:source-locked typed Staff lifecycle fact read grants no cross-owner mutation authority"),
    ),
    "infrastructure/mysql/service_before_replacement_loader.py": (
        "08310ae6d43bd37f3a4d572d97a0f464822685c4d75352ed14322d22f2356539",
        frozenset({"MySqlServiceBeforeReplacementLoader._all"}),
        ("scheduling", "bounded Service-Before-Replacement composite owner-fact read", "typed ServiceBeforeReplacementWorkflow", "retain_restricted:source-locked fixed reads and locks use a borrowed connection and grant no cross-owner writer authority"),
    ),
    "infrastructure/mysql/staff_summary_query_repository.py": (
        "8233e5b639aa6111f4c90c4e3e46863bbd510b8f602ded8ec56ba20d5afa15dc",
        frozenset({"MySqlStaffSummaryQueryRepository.fetch_page"}),
        ("staff_operations", "bounded Staff summary query", "StaffSummaryQueryService", "retain_restricted:source-locked fixed paginated SELECT grants no mutation authority"),
    ),
    "subsystems/scheduling/occupancy_mutex.py": (
        "b9eed48f3765e74acac1b72fbeb174207e93146d0a5016d775276b78d47a6dd0",
        frozenset({"lock_staff_occupancy_mutex"}),
        ("scheduling", "Scheduling occupancy serialization read lock", "availability lock, Orders cancellation, service replacement, and staff availability workflows", "retain_restricted:source-locked SELECT FOR UPDATE helper uses the caller transaction and grants no writer authority"),
    ),
    "infrastructure/mysql/client_beclass_workbook_import_repository.py": (
        "49f4b32da6a3a0420b86255c657f206093de5d9f55e0fe76bd90a5d7af64876a",
        frozenset({"ClientBeClassWorkbookImportRepository._claim", "ClientBeClassWorkbookImportRepository._save_receipt", "ClientBeClassWorkbookImportRepository.create_bound_source_if_absent"}),
        ("case_import", "temporary authenticated Client BeClass workbook intake", "ClientBeClassWorkbookImportService row and workbook transactions", "retain_restricted:source-locked command claim, temporary receipt, and Case Import source binding remain restricted historical intake and may not become a generic current profile writer"),
    ),
    "infrastructure/mysql/scheduling_bootstrap_writer.py": (
        "c774d6254ccff19a0fe75a2fdfbf0c6422f6eda49ddba1c84689e0077e8d8b64",
        frozenset({"_activate_generation", "_append_review_if_absent", "_attach_assignment", "_attach_schedules", "_insert_aggregate", "_insert_buffers", "_insert_generation", "_insert_occupancy"}),
        ("global_migration", "guarded Scheduling generation bootstrap writer", "migrate_scheduling_generation_bootstrap operator workflow", "retain_restricted:source-locked maintenance/migration symbols remain operator-only and subject to target, plan, backup, apply, verify, replay, receipt, and authority gates"),
    ),
    "subsystems/scheduling/availability_lock_acquisition_workflow.py": (
        "eebff3a7f5c629ba772c2d0c008706284c7f4e7caadbcfae7f72e8a42d0f16bf",
        frozenset({"_occupancy_conflicts"}),
        ("scheduling", "bounded Scheduling occupancy conflict reads and locks", "typed availability-lock acquisition API", "retain_restricted:source-locked dynamic placeholders are fixed SELECT/FOR UPDATE reads and grant no independent writer authority"),
    ),
    "subsystems/scheduling/availability_lock_cancellation_workflow.py": (
        "caedac8c2e3091d83905c38d1e7d21f3ac21d85e1ffd17cfc386c0c34923ab74",
        frozenset({"_load_event_for_key"}),
        ("scheduling", "bounded Scheduling availability-lock cancellation replay read", "Order Cancellation workflow through explicit Scheduling delegate", "retain_restricted:source-locked fixed replay query grants no independent writer authority"),
    ),
    "infrastructure/mysql/import_warning_auto_resolution.py": (
        "17f6f54d133d97b7670ae217e08e33c9034db415519453ff8faf67fb2ef18496",
        frozenset({"_load_tasks"}),
        ("case_onboarding", "bounded Case Onboarding import-warning task read", "HCM resubmission outbox consumer", "retain_restricted:source-locked fixed warning occurrence/current-task query grants no independent writer authority"),
    ),
    "infrastructure/mysql/import_warning_tracking_repository.py": (
        "406887d9898984e91acb1ab13fd1338cadf9ec09e6aa4b71d252d24e18a0f388",
        frozenset({"MySqlImportWarningTrackingRepository.load_task"}),
        ("case_onboarding", "bounded Case Onboarding import-warning task read and lock", "typed Import Warning Tracking Query/Preview/Apply", "retain_restricted:source-locked fixed query plus optional FOR UPDATE grants no independent writer authority"),
    ),
    "infrastructure/mysql/historical_baseline_client_finance_owner_adapter.py": (
        "06343b08a1bd75dd718a6dd509abbfe690fd6c15801a3bb31456379fbfcb5578",
        frozenset({"MySqlHistoricalBaselineClientFinanceOwnerAdapter._read_case", "MySqlHistoricalBaselineClientFinanceOwnerAdapter._read_terms"}),
        ("client_finance", "bounded historical baseline Client Finance owner-fact query adapter", "HistoricalBaselineOwnerVectorV2Query", "retain_restricted:source-locked fixed owner-table reads use a borrowed connection and grant no mutation authority"),
    ),
    "scripts/backfill_canonical_accounting_projections.py": (
        "99e9fb79d84ac8b28a608010112251a45b0fb4163d2f0cd4368cbe533ce6edd7",
        frozenset({"_apply", "_insert_client_projection", "_insert_staff_projection", "run_migration"}),
        ("global_migration", "guarded accounting projection backfill migration", "operator CLI restricted to explicit disposable lu_test target", "retain_restricted:source-locked migration requires target, dry-run plan, backup, exact apply confirmation, verify, replay, receipt, and authority gates; no production writer authority is granted"),
    ),
    "infrastructure/mysql/historical_order_review_remediation_repository.py": (
        "37a74363064dbcc23a7b2dd124df9c0193f917abc66bf61bd3c42b5cc1cb96cc",
        frozenset({"MySqlHistoricalOrderReviewRemediationRepository.load_context"}),
        ("orders", "bounded historical Orders review-remediation context read", "typed historical Orders remediation Query/Preview/Apply", "retain_restricted:source-locked Orders and current-anomaly context reads grant no Anomalies writer authority"),
    ),
    "infrastructure/mysql/matching_coordination_repository.py": (
        "5468d3ce405340ef15b8f47f11b96e546ec4578a78c94b213b403e7e69771f55",
        frozenset({"MySqlMatchingCoordinationRepository._all", "MySqlMatchingCoordinationRepository._one"}),
        ("scheduling", "bounded Scheduling Matching Coordination repository read", "typed Matching Coordination Query/Preview/Apply and Service-Before-Replacement composition", "retain_restricted:source-locked fixed-query reads grant no independent writer authority"),
    ),
    "infrastructure/mysql/customer_service_escalation_repository.py": (
        "13e2536420ae383c9bde29fc9fa7fcee096616e1c406e1fadfc4099db9cb00ba",
        frozenset({"MySqlCustomerServiceEscalationRepository._one", "MySqlCustomerServiceEscalationRepository._receipt_row"}),
        ("customer_service", "bounded Customer Service escalation repository read", "typed Customer Service escalation Query/Preview/Apply", "retain_restricted:source-locked fixed-query row and receipt reads grant no independent writer authority"),
    ),
    "infrastructure/db/contract_external_signing_repository.py": (
        "715def0bda249e10b685782ecf2ca846b926582520ffd08ccb83c15c03c4ddc1",
        frozenset({"MySqlContractExternalSigningRepository._all", "MySqlContractExternalSigningRepository._one"}),
        ("contract_signing", "bounded Contract Signing external-session repository read", "typed Contract External Signing and recovery workflows", "retain_restricted:source-locked fixed-query reads grant no independent writer authority"),
    ),
    "infrastructure/db/contract_unsigned_pdf_repository.py": (
        "2227bb7cc251ac9f24e82df2c25382c7b121f8a5a86c2ae9d317e66e3361ffda",
        frozenset({"MySqlContractUnsignedPdfRepository._one"}),
        ("contract_signing", "bounded Contract Signing unsigned-PDF repository read", "typed unsigned-PDF generation and persistence workflow", "retain_restricted:source-locked fixed-query read grants no independent writer authority"),
    ),
    "infrastructure/mysql/historical_operational_baseline_repository.py": (
        "c693c9aab4e385af74d99a904c48eb091f824a098d14a207920a500597a105d8",
        frozenset({"MySqlHistoricalOperationalBaselineOutbox.append", "MySqlHistoricalOperationalBaselineRepository.append_baseline", "MySqlHistoricalOperationalBaselineRepository.find_receipt", "MySqlHistoricalOperationalBaselineRepository.load_facts", "MySqlHistoricalOperationalBaselineRepository.save_receipt"}),
        ("orders", "historical-only Orders operational baseline transaction", "authenticated historical operational baseline Query/Preview/Apply", "retain_restricted:source-locked append-only baseline, receipt, read, and baseline-owned outbox symbols remain historical-only and never become a daily writer"),
    ),
    "infrastructure/db/controlled_file_repository.py": (
        "adac676918a117074f5d4fdb8683a69bf770ec3b16d0ec904efeac709a0b3e7b",
        frozenset({"MySqlControlledFileWorkflowRepository.find_receipt", "MySqlControlledFileWorkflowRepository.load_cleanup", "MySqlControlledFileWorkflowRepository.load_staging", "MySqlControlledFileWorkflowRepository.owner_subject_exists"}),
        ("controlled_files", "bounded Controlled Files repository read inside workflow", "Controlled Files workflow, cleanup, reconciliation, and GC applications", "retain_restricted:source-locked fixed-table or owner-allowlisted read is not an independent mutation writer"),
    ),
    "infrastructure/mysql/client_deposit_reversal_repository.py": (
        "ab46f559639c4f241d0fc82dd917ba3a2028d0ab3f8e1c85442522a114bbfee4",
        frozenset({"MySqlClientDepositReversalRepository.load"}),
        ("client_finance", "bounded deposit reversal facts read and lock", "DepositReversalWorkflow Preview/Apply", "retain_restricted:source-locked dynamic suffix is only FOR UPDATE over fixed Client Finance and owner fact tables"),
    ),
    "infrastructure/mysql/finance_import_repository.py": (
        "d7d174528580740b86654543ec415d0d322fb2cb3a1155129e69a0df742b2432",
        frozenset({"MySqlFinanceImportRepository.load_refund_return_review", "_load_active_alert", "_load_batch_facts", "_load_client_and_staff_obligations", "_load_correction_facts", "_load_government_subsidy_obligations"}),
        ("finance_import", "bounded Finance Import and owner-fact read inside Preview/Apply", "Finance Import, correction, and refund-review workflows", "retain_restricted:source-locked dynamic SQL uses fixed constants and bounded IN placeholders; no independent writer authority"),
    ),
}

EXACT_IDENTITY_REVIEWS: dict[str, tuple[str, str, str, str]] = {
    "infrastructure/mysql/admin_command_repository.py:AdminCommandRepository._load_one:execute:DYNAMIC:unknown:6714e6e1b8bce7b4:1": (
        "global_operations", "bounded legacy admin command read", "Orders client-name maintenance and inactive holiday helper", "retain_restricted:exact fixed clients/holidays read grants no generic source mutation authority"
    ),
    "infrastructure/mysql/admin_command_repository.py:AdminCommandRepository.save_receipt:execute:INSERT:admin_command_receipts:2e565cbed3c245e1:1": (
        "global_operations", "bounded admin command receipt persistence", "typed client-name maintenance and blocked generic source correction", "retain_restricted:exact shared receipt remains guarded; generic load/update identities stay unclassified pending owning-domain replacements"
    ),
    "infrastructure/mysql/finance_import_repository.py:MySqlFinanceImportRepository.append_refund_return_review:execute:INSERT:client_refund_return_review_events:bd18c8f3e0b6cae2:1": (
        "client_finance", "Client Finance refund-return review event inside Finance Import outer Unit of Work", "typed RefundReturnReviewWorkflow", "retain_canonical:exact Client Finance review event uses the caller-owned transaction"
    ),
    "infrastructure/mysql/finance_import_repository.py:MySqlFinanceImportRepository.save_refund_return_review_receipt:execute:INSERT:client_refund_return_review_receipts:73e41bf7b1411ef0:1": (
        "client_finance", "Client Finance refund-return review receipt inside Finance Import outer Unit of Work", "typed RefundReturnReviewWorkflow", "retain_canonical:exact Client Finance review receipt uses the caller-owned transaction"
    ),
    "infrastructure/mysql/hcm_resubmission_repository.py:MySqlHcmResubmissionRepository.apply_field_correction:execute:INSERT:case_import_hcm_correction_events:eeb562d1b19ddf45:1": (
        "case_import", "Case Import HCM canonical review correction evidence inside workflow outer Unit of Work", "typed HCM Resubmission Preview/Apply", "retain_canonical:exact Case Import correction event records canonical review identity and append-only expected/resulting review versions using the caller-owned transaction"
    ),
    "infrastructure/mysql/hcm_resubmission_repository.py:MySqlHcmResubmissionRepository.load_facts:execute:DYNAMIC:unknown:8533fe213130e092:1": (
        "case_import", "bounded canonical HCM review and owner-fact query with optional lock", "typed HCM Resubmission Preview/Apply", "retain_restricted:exact fixed Case Import review, binding, correction-event, Client, and Orders reads grant no independent mutation authority"
    ),
    "infrastructure/mysql/admin_command_repository.py:AdminCommandRepository.delete_holiday:execute:DELETE:holidays:db0b8f0c7231ecbc:1": (
        "scheduling", "Scheduling holiday mutation via bounded Admin Command application", "typed admin holiday command", "retain_canonical:exact Scheduling-owned holiday delete; shared generic admin identities remain unclassified"
    ),
    "infrastructure/mysql/admin_command_repository.py:AdminCommandRepository.upsert_holiday:execute:INSERT:holidays:2343254d68db033e:1": (
        "scheduling", "Scheduling holiday mutation via bounded Admin Command application", "typed admin holiday command", "retain_canonical:exact Scheduling-owned holiday upsert; shared generic admin identities remain unclassified"
    ),
    "infrastructure/mysql/admin_command_repository.py:AdminCommandRepository.update_client_name:execute:UPDATE:clients:fcfb4a0475e9df26:1": (
        "orders", "Orders client-name mutation via bounded Admin Command application", "typed admin client-name command", "retain_canonical:exact Orders-owned client-name update; no generic client editor authority is granted"
    ),
    "infrastructure/mysql/service_date_confirmation_repository.py:MySqlServiceDateConfirmationRepository.save:execute:INSERT:confirmed_service_date_receipts:b5f77edb43f88e5f:1": (
        "orders", "Orders Confirmed Service Dates receipt mutation inside workflow outer Unit of Work", "typed Service Date Confirmation Apply", "retain_canonical:exact Orders-owned receipt identity; repository never commits"
    ),
    "infrastructure/mysql/service_date_confirmation_repository.py:MySqlServiceDateConfirmationRepository.save:execute:INSERT:confirmed_service_date_versions:c7f384818ee43ace:1": (
        "orders", "Orders Confirmed Service Dates version mutation inside workflow outer Unit of Work", "typed Service Date Confirmation Apply", "retain_canonical:exact Orders-owned version identity; repository never commits"
    ),
    "infrastructure/mysql/service_date_confirmation_repository.py:MySqlServiceDateConfirmationRepository.save:execute:UPDATE:confirmed_service_date_versions:798e57f84b6734b1:1": (
        "orders", "Orders Confirmed Service Dates version mutation inside workflow outer Unit of Work", "typed Service Date Confirmation Apply", "retain_canonical:exact Orders-owned version identity; repository never commits"
    ),
    "infrastructure/mysql/service_date_confirmation_repository.py:MySqlServiceDateConfirmationRepository.save:executemany:INSERT:confirmed_service_date_days:fcdb026257bc5028:1": (
        "orders", "Orders Confirmed Service Dates day mutation inside workflow outer Unit of Work", "typed Service Date Confirmation Apply", "retain_canonical:exact Orders-owned confirmed-day identity; repository never commits"
    ),
    "infrastructure/mysql/finance_import_repository.py:MySqlFinanceImportRepository.append_refund_return_review:execute:INSERT:finance_import_outbox:7bb474ba6a87598f:1": (
        "finance_import",
        "Finance Import refund-review outbox append inside workflow outer Unit of Work",
        "typed Finance Import refund-review workflow",
        "retain_canonical:exact finance_import_outbox identity is Finance Import-owned; sibling Client Finance review-event and receipt identities remain unclassified pending cross-domain writer authority",
    ),
}


def _load(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _review(record: dict[str, object]) -> tuple[str, str, str, str]:
    path = str(record["relative_path"])
    identity_review = EXACT_IDENTITY_REVIEWS.get(str(record["identity"]))
    if identity_review is not None:
        return identity_review
    exact = _task97_exact_review(path, str(record["symbol"]))
    if exact is not None:
        return exact
    exact = _accepted_commit_review(str(record["identity"]))
    if exact is not None:
        return exact
    exact = _exact_source_review(path, str(record["symbol"]), EXACT_SOURCE_RESTRICTED_REVIEWS)
    if exact is not None:
        return exact
    exact = _exact_source_review(path, str(record["symbol"]), EXACT_SOURCE_REVIEWS)
    if exact is not None:
        return exact
    reviewed = _current_runtime_review(path)
    if reviewed is not None:
        return reviewed
    reviewed = _owner_review_registry().get(path)
    if reviewed is not None:
        return reviewed
    if path == "infrastructure/mysql/provisional_registration_repository.py":
        return _provisional_registration_review()
    if path == "subsystems/case_import/provisional_registration_application.py":
        return _provisional_registration_review()
    if path == "line/line_bot.py":
        return _legacy_line_bot_review(str(record["symbol"]))
    if path == "line/worker.py":
        return _line_worker_review()
    if path.startswith("subsystems/line/"):
        return _typed_line_review(path)
    if record.get("owner_candidate") == "payroll":
        return (
            "payroll",
            "typed Payroll repository or application transaction",
            "typed Payroll application composition and workflow",
            "retain_canonical:Payroll owns its calculation facts, receipts, outbox, and rebuild transitions",
        )
    return _service_review(path)


def _exact_source_review(
    path: str,
    symbol: str,
    reviews: dict[str, tuple[str, frozenset[str], tuple[str, str, str, str]]],
) -> tuple[str, str, str, str] | None:
    reviewed = reviews.get(path)
    if reviewed is None:
        return None
    expected_sha256, symbols, disposition = reviewed
    if symbol not in symbols:
        return None
    if sha256((ROOT / path).read_bytes()).hexdigest() != expected_sha256:
        return None
    return disposition


def _accepted_commit_review(identity: str) -> tuple[str, str, str, str] | None:
    """Join only an exact identity accepted by the Task 97 commit receipt."""
    if not COMMIT_DISPOSITIONS.exists():
        return None
    artifact = json.loads(COMMIT_DISPOSITIONS.read_text(encoding="utf-8"))
    if artifact.get("terminal_status") != "passed":
        return None
    accepted = {
        str(entry["identity"]): entry
        for entry in artifact.get("entries", [])
        if entry.get("classification") == "application_owned_legitimate_outer_uow"
    }
    entry = accepted.get(identity)
    if entry is None:
        return None
    owner = str(entry["owner"])
    layer = str(entry["layer"])
    disposition = "retain_restricted" if layer in {"maintenance", "worker"} else "retain_canonical"
    return (
        owner,
        f"exact Task 97 accepted {layer} commit boundary",
        f"task97_repository_commit_dispositions_v1 exact identity {identity}",
        f"{disposition}:exact commit fingerprint, symbol, owner, and layer are accepted by the current Task 97 receipt; no path-wide inference",
    )


def _task97_exact_review(
    path: str, symbol: str
) -> tuple[str, str, str, str] | None:
    """Exact Task 97 decisions that must not be widened to a whole module."""
    canonical: dict[tuple[str, str], tuple[str, str]] = {
        ("api/dependencies/contract_external_signing.py", "ContractExternalSigningApplication.download_unsigned"): (
            "contract_signing", "Contract Signing application transaction"
        ),
        ("infrastructure/mysql/unit_of_work.py", "MySqlUnitOfWork.commit"): (
            "global_infrastructure", "explicit caller-owned outer Unit of Work"
        ),
        ("infrastructure/mysql/service_day_log_repository.py", "MySqlServiceDayLogRepository.submit"): (
            "scheduling", "Scheduling Service Day Log repository inside caller UoW"
        ),
        ("infrastructure/mysql/service_day_log_repository.py", "MySqlServiceDayLogRepository.load_assignment"): (
            "scheduling", "Scheduling Service Day Log assignment visibility query inside workflow Preview/Apply"
        ),
        ("infrastructure/mysql/service_day_log_repository.py", "MySqlServiceDayLogRepository._attach_controlled_files"): (
            "scheduling", "Scheduling Service Day Log attachment bridge inside caller UoW"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.create_finalize_intent"): (
            "controlled_files", "Controlled Files finalize intent inside Scheduling caller UoW"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.create_scheduling_reference"): (
            "controlled_files", "Controlled Files Scheduling reference inside caller UoW"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.acquire_lease"): (
            "controlled_files", "Controlled Files bounded finalize/GC lease state"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.claim_finalize_intent"): (
            "controlled_files", "Controlled Files bounded finalize claim state"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.mark_finalize_available"): (
            "controlled_files", "Controlled Files integrity-verified finalize state"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.mark_finalize_reconciliation_required"): (
            "controlled_files", "Controlled Files typed reconciliation state"
        ),
        ("infrastructure/db/controlled_file_reference_finalize_repository.py", "MySqlControlledFileReferenceFinalizeRepository.release_lease"): (
            "controlled_files", "Controlled Files bounded lease release state"
        ),
        ("infrastructure/mysql/client_hcm_correction_adapter.py", "MySqlClientHcmCorrectionAdapter.apply_in_current_uow"): (
            "clients", "Client HCM correction command inside Case Import caller UoW"
        ),
        ("infrastructure/mysql/current_anomaly_issue_repository.py", "MySqlCurrentIssueRepository.complete_recheck_intent"): (
            "anomalies", "current projection intent completion inside Anomaly application UoW"
        ),
        ("infrastructure/mysql/current_anomaly_issue_repository.py", "MySqlCurrentIssueRepository.delete_current"): (
            "anomalies", "current-only anomaly projection deletion inside application UoW"
        ),
        ("infrastructure/mysql/current_anomaly_issue_repository.py", "MySqlCurrentIssueRepository.upsert_current"): (
            "anomalies", "current-only anomaly projection upsert inside application UoW"
        ),
        ("infrastructure/mysql/hcm_resubmission_repository.py", "MySqlHcmResubmissionRepository.append_outbox"): (
            "case_import", "Case Import correction outbox inside workflow UoW"
        ),
        ("infrastructure/mysql/hcm_resubmission_repository.py", "MySqlHcmResubmissionRepository.save_receipt"): (
            "case_import", "Case Import correction receipt inside workflow UoW"
        ),
        ("infrastructure/mysql/line_notification_repository.py", "MySqlLineNotificationRepository.cancel_service_day_log_reminders"): (
            "line_delivery", "LINE delivery intent/task cancellation inside Service Day notification-stop caller UoW"
        ),
        ("infrastructure/mysql/line_notification_repository.py", "MySqlLineNotificationRepository.cancel_service_day_log_reminders_for_assignments"): (
            "line_delivery", "LINE delivery intent/task cancellation inside Scheduling rebuild invalidation caller UoW"
        ),
        ("infrastructure/mysql/service_day_checkpoint_repository.py", "MySqlServiceDayCheckpointRepository.append_checkpoint"): (
            "scheduling", "Scheduling Service Day Checkpoint repository inside MySqlServiceDayCheckpointWorker outer UoW"
        ),
        ("infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py", "MySqlSchedulingCheckpointNotificationSourceRepository.mark_published"): (
            "scheduling", "Scheduling checkpoint notification-source outbox state inside MySqlSchedulingCheckpointNotificationSourceWorker outer UoW"
        ),
        ("infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py", "MySqlSchedulingCheckpointNotificationSourceRepository.mark_retry_or_failed"): (
            "scheduling", "Scheduling checkpoint notification-source outbox state inside MySqlSchedulingCheckpointNotificationSourceWorker outer UoW"
        ),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.claim_due"): (
            "scheduling", "Scheduling Service Day Log notification-stop outbox state inside MySqlServiceDayLogNotificationStopWorker outer UoW"
        ),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.mark_published"): (
            "scheduling", "Scheduling Service Day Log notification-stop outbox state inside MySqlServiceDayLogNotificationStopWorker outer UoW"
        ),
        ("infrastructure/mysql/service_day_log_notification_stop_repository.py", "MySqlServiceDayLogNotificationStopRepository.mark_retry_or_failed"): (
            "scheduling", "Scheduling Service Day Log notification-stop outbox state inside MySqlServiceDayLogNotificationStopWorker outer UoW"
        ),
        ("subsystems/case_import/hcm_beclass_reconciliation.py", "CaseImportReconciliationApplication.reconcile"): (
            "case_import", "Case Import reconciliation outer Unit of Work"
        ),
        ("subsystems/anomalies/current_issue_recheck.py", "CurrentIssueApplication.mutate_owner_with_recheck_intent"): (
            "anomalies", "owner mutation and bounded recheck-intent application transaction"
        ),
        ("subsystems/anomalies/current_issue_recheck.py", "CurrentIssueApplication.reconcile"): (
            "anomalies", "current projection reconcile and intent-complete application transaction"
        ),
        ("subsystems/scheduling/service_day_log_workflow.py", "ServiceDayLogApplication.apply"): (
            "scheduling", "Scheduling Service Day Log application transaction"
        ),
    }
    key = (path, symbol)
    if key in canonical:
        owner, boundary = canonical[key]
        if path == "infrastructure/mysql/line_notification_repository.py":
            caller = (
                "subsystems/line/service_day_log_notification_stop.py::ServiceDayLogNotificationStopApplication.apply"
                if symbol == "MySqlLineNotificationRepository.cancel_service_day_log_reminders"
                else "subsystems/line/scheduling_rebuild_notification_invalidation.py::SchedulingRebuildNotificationInvalidationApplication.apply"
            )
            evidence = (
                "retain_canonical:LINE owns notification delivery intent/task state only; Scheduling owns the Service Day "
                "completion fact and assignment lineage; Staff Operations remains actor/entry"
            )
        elif path == "infrastructure/mysql/service_day_log_repository.py" and symbol == "MySqlServiceDayLogRepository.load_assignment":
            caller = "subsystems/scheduling/service_day_log_workflow.py::ServiceDayLogWorkflow Preview/Apply"
            evidence = (
                "retain_canonical:Scheduling owns Service Day assignment visibility; Staff Operations remains actor/entry, "
                "and LINE is limited to identity, media, and delivery"
            )
        elif path == "infrastructure/mysql/service_day_checkpoint_repository.py":
            caller = "infrastructure/mysql/service_day_checkpoint_worker.py::MySqlServiceDayCheckpointWorker.run_once"
            evidence = (
                "retain_canonical:Scheduling owns Service Day checkpoint fact, event, and outbox; Staff Operations remains "
                "actor/entry, and LINE is limited to identity, media, and delivery"
            )
        elif path == "infrastructure/mysql/scheduling_checkpoint_notification_source_repository.py":
            caller = "infrastructure/mysql/scheduling_checkpoint_notification_source_worker.py::MySqlSchedulingCheckpointNotificationSourceWorker.run_once"
            evidence = (
                "retain_canonical:Scheduling owns checkpoint outbox state; Staff Operations remains actor/entry, and LINE "
                "is limited to identity, media, and delivery"
            )
        elif path == "infrastructure/mysql/service_day_log_notification_stop_repository.py":
            caller = "infrastructure/mysql/service_day_log_notification_stop_worker.py::MySqlServiceDayLogNotificationStopWorker.run_once"
            evidence = (
                "retain_canonical:Scheduling owns Service Day Log outbox state; Staff Operations remains actor/entry, and "
                "LINE is limited to identity, media, and delivery"
            )
        else:
            caller = f"Task97 exact application/UoW evidence for {path}::{symbol}"
            evidence = "retain_canonical:exact Task97 owner and transaction boundary verified; no module-wide inference"
        return (
            owner,
            boundary,
            caller,
            evidence,
        )
    restricted_owner: dict[tuple[str, str], tuple[str, str]] = {
        (
            "infrastructure/mysql/current_anomaly_issue_repository.py",
            "MySqlCurrentIssueRepository.list_current",
        ): ("anomalies", "bounded current-only anomaly projection query"),
        (
            "infrastructure/mysql/current_anomaly_issue_repository.py",
            "MySqlCurrentIssueRepository.query_current_page",
        ): ("anomalies", "bounded current-only anomaly projection query"),
    }
    if key in restricted_owner:
        owner, boundary = restricted_owner[key]
        return (
            owner,
            boundary,
            f"Task97 exact bounded read evidence for {path}::{symbol}",
            "retain_restricted:exact owner-scoped read grants no independent mutation authority",
        )
    restricted: dict[tuple[str, str], str] = {
        ("api/dependencies/line_worker_operation.py", "_write_heartbeat"): "LINE worker heartbeat short transaction",
        ("api/dependencies/private_operations.py", "_write_durable_job_heartbeat"): "private durable-job heartbeat short transaction",
        ("api/dependencies/private_operations.py", "record_monitor_cycle"): "private monitor-cycle short transaction",
        ("api/dependencies/runtime_heartbeat.py", "record_runtime_heartbeat"): "runtime heartbeat short transaction",
        ("infrastructure/mysql/line_notification_reconciliation_worker.py", "MySqlLineNotificationReconciliationWorker.run_once"): "LINE notification reconciliation worker transaction",
        ("infrastructure/mysql/scheduling_checkpoint_notification_source_worker.py", "MySqlSchedulingCheckpointNotificationSourceWorker.run_once"): "Scheduling checkpoint notification worker transaction",
        ("infrastructure/mysql/scheduling_rebuild_notification_invalidation_worker.py", "MySqlSchedulingRebuildNotificationInvalidationWorker.run_once"): "Scheduling rebuild invalidation worker transaction",
        ("infrastructure/mysql/service_day_log_notification_stop_worker.py", "MySqlServiceDayLogNotificationStopWorker.run_once"): "Service Day Log notification-stop worker transaction",
    }
    if key in restricted:
        return (
            "global_operations" if path.startswith("api/dependencies/") else "worker_owner",
            restricted[key],
            f"Task97 exact bounded worker evidence for {path}::{symbol}",
            "retain_restricted:independent short worker/heartbeat transaction; not a domain repository commit",
        )
    return None


def _current_runtime_review(path: str) -> tuple[str, str, str, str] | None:
    metadata = {
        "infrastructure/mysql/admin_capability_grant_repository.py": (
            "access_control", "retired legacy capability-grant transaction",
            "no runtime caller; capability-grant routes return HTTP 410",
            "migrate_then_remove:equal business access no longer consumes per-user grants; physical schema retirement requires a separate approved migration",
        ),
        "infrastructure/mysql/anomaly_registry_repository.py": (
            "anomalies", "typed anomaly workflow transaction",
            "subsystems/anomalies/current_issue_recheck.py", "retain_canonical:current-only anomaly reconciliation remains Application-owned while legacy projection callers are retired",
        ),
        "infrastructure/mysql/background_job_repository.py": (
            "global_infrastructure", "durable job query adapter",
            "subsystems/jobs/durable_job_worker.py", "retain_restricted:dynamic query helper is constrained to the versioned durable-job repository",
        ),
        "infrastructure/mysql/historical_reprocess_repository.py": (
            "finance_import", "typed Historical Reprocess outer transaction",
            "api/dependencies/finance_import.py", "retain_canonical:classification selection, run, receipt, outbox, and version update stay inside the owning workflow",
        ),
        "infrastructure/mysql/knowledge_retrieval_repository.py": (
            "knowledge_retrieval", "typed knowledge review or publication transaction",
            "api/routes/knowledge_retrieval.py", "retain_canonical:provenance item event, publication transition, and receipt are owned by Knowledge Retrieval",
        ),
        "subsystems/finance_import/ingestion.py": (
            "finance_import", "typed Finance Import ingestion transaction",
            "api/dependencies/finance_import.py",
            "retain_canonical:batch contract, classification event, receipt, outbox, and independent failed-attempt audit are one Finance Import workflow boundary",
        ),
        "scripts/migrate_admin_capability_grants_schema.py": (
            "global_infrastructure", "versioned additive release migration",
            "preserve-data release manifest", "retain_restricted:operator-run additive schema upgrade is bounded by signed release artifacts",
        ),
        "scripts/migrate_order_contract_identity.py": (
            "global_infrastructure", "versioned contract identity migration",
            "preserve-data release manifest", "retain_restricted:operator-run schema migration is bounded by its explicit retirement contract",
        ),
        "subsystems/access/authentication_session.py": (
            "access_control", "authenticated session and audit transaction",
            "api/dependencies/admin_auth.py", "retain_canonical:session lifecycle and privacy-masked audit append are Access Control facts",
        ),
        "subsystems/access/security_audit_query.py": (
            "access_control", "security-audit retention transaction",
            "api/main.py lifespan worker", "retain_canonical:expired online audit rows move append-only into archive without deleting archive evidence",
        ),
        "subsystems/line/rich_menu_publication_workflow.py": (
            "line_integration", "typed rich-menu preview and confirmation transaction",
            "api/routes/line_rich_menus.py", "retain_canonical:preview receipt and confirmed publication job are owned by the LINE publication workflow",
        ),
        "subsystems/orders/client_finance_outbox_consumer.py": (
            "client_finance", "committed Client Finance outbox recovery transaction",
            "subsystems/orders/client_finance_outbox_consumer.py", "retain_canonical:consumer may only advance committed outbox delivery state",
        ),
    }
    return metadata.get(path)


def _owner_review_registry() -> dict[str, tuple[str, str, str, str]]:
    """Exact-path owner decisions for the WP63 merge-introduced review queue."""
    canonical = "retain_canonical:typed owner persists root facts, events, receipts, or outbox within its reviewed transaction"
    restricted = "retain_restricted:operator or worker state is bounded to this explicit maintenance or execution entry"
    return {
        "api/dependencies/line_runtime.py": ("line_ingress", "LINE runtime security-receipt transaction", "api/main.py LINE runtime dependency", canonical),
        "api/routes/clients.py": ("client_identity", "legacy client identity compatibility transaction", "api/main.py mounts clients router", "migrate_then_remove:typed LINE identity workflow is the canonical replacement; removal requires a separate entrypoint package"),
        "api/routes/line_staff_self_service.py": ("line_self_service", "read-only self-service request transaction", "api/main.py mounts LINE staff self-service router", restricted),
        "api/routes/runtime_health.py": ("global_operations", "runtime-health observation transaction", "api/main.py mounts runtime health router", restricted),
        "infrastructure/mysql/assignment_plan_repository.py": ("scheduling", "typed Assignment Plan outer transaction", "Scheduling assignment-plan workflows", canonical),
        "infrastructure/mysql/case_import_repository.py": ("case_import", "typed Case Import outer transaction", "api/dependencies/case_import.py", canonical),
        "infrastructure/mysql/client_over_refund_recovery_repository.py": ("client_finance", "typed Client Finance recovery transaction", "ClientOverRefundRecovery workflows", canonical),
        "infrastructure/mysql/client_receipt_reconciliation_repository.py": ("client_finance", "typed receipt reconciliation transaction", "Client Finance reconciliation workflow", canonical),
        "infrastructure/mysql/client_refund_reversal_repository.py": ("client_finance", "typed refund reversal transaction", "Client Refund reversal workflow", canonical),
        "infrastructure/mysql/customer_service_repository.py": ("customer_service", "typed Customer Service ticket transaction", "subsystems/customer_service/application.py", canonical),
        "infrastructure/mysql/financial_adjustment_repository.py": ("client_finance", "typed financial adjustment transaction", "Client Finance adjustment workflow", canonical),
        "infrastructure/mysql/government_payer_master_repository.py": ("government_subsidy", "typed payer-master version transaction", "GovernmentPayerMasterWorkflow", canonical),
        "infrastructure/mysql/government_return_outbound_overage_anomaly_source.py": ("anomalies", "bounded government-return anomaly projection transaction", "Anomalies scheduled source scan", restricted),
        "infrastructure/mysql/government_subsidy_repository.py": ("government_subsidy", "typed Government Subsidy outer transaction", "Government Subsidy overpayment workflows", canonical),
        "infrastructure/mysql/hcm_import_review_repository.py": ("case_import", "typed HCM review root and outbox transaction", "subsystems/case_import/hcm_import_review_intake.py", canonical),
        "infrastructure/mysql/line_configuration_publication_repository.py": ("line_integration", "typed LINE configuration and publication transaction", "LINE configuration and Rich Menu applications", canonical),
        "infrastructure/mysql/line_delivery_task_repository.py": ("line_delivery", "typed delivery task state transaction", "LINE delivery worker and admin application", canonical),
        "infrastructure/mysql/line_identity_management_repository.py": ("line_identity", "typed identity revocation transaction", "LineIdentityManagementApplication and worker", canonical),
        "infrastructure/mysql/line_identity_owner_adapters.py": ("line_identity", "borrowed LINE identity owner transaction", "LineIdentityApplication", canonical),
        "infrastructure/mysql/line_identity_review_repository.py": ("line_identity", "typed identity binding and review transaction", "LINE identity and review applications", canonical),
        "infrastructure/mysql/line_media_order_group_repository.py": ("line_integration", "typed media and order-group transaction", "LINE media and order-group applications", canonical),
        "infrastructure/mysql/line_order_group_adapters.py": ("orders", "borrowed Orders LINE audience projection transaction", "LineOrderGroupApplication", canonical),
        "infrastructure/mysql/line_platform_identity_repository.py": ("line_identity", "typed platform identity and friend-state transaction", "LINE webhook identity applications", canonical),
        "infrastructure/mysql/line_receipt_outbox_audit.py": ("line_integration", "caller-owned LINE receipt, audit, and outbox transaction", "typed LINE applications and workers", canonical),
        "infrastructure/mysql/line_runtime_repository.py": ("line_operations", "runtime heartbeat and security evidence transaction", "LINE runtime health and worker", restricted),
        "infrastructure/mysql/line_webhook_inbox_repository.py": ("line_ingress", "typed webhook inbox claim transaction", "LineWebhookIntake and LineWebhookEventConsumer", canonical),
        "infrastructure/mysql/matching_notification_repository.py": ("scheduling", "typed matching notification transaction", "MatchingNotificationApplication", canonical),
        "infrastructure/mysql/order_contract_completion_repository.py": ("orders", "typed contract-completion outer transaction", "Contract Completion workflow", canonical),
        "infrastructure/mysql/order_terms_read_model.py": ("orders", "read-model query boundary", "Orders terms query", restricted),
        "infrastructure/mysql/runtime_monitor_repository.py": ("global_operations", "runtime monitor observation and alert-intent transaction", "scripts/run_service_monitor.py", restricted),
        "infrastructure/mysql/staff_overpayment_recovery_repository.py": ("staff_payables", "typed Staff Payables recovery transaction", "StaffOverpaymentRecovery workflows", canonical),
        "infrastructure/mysql/staff_historical_adoption_repository.py": ("case_import", "typed Staff historical adoption transaction", "subsystems/case_import/staff_historical_adoption.py", canonical),
        "infrastructure/mysql/staff_payout_repository.py": ("staff_payables", "typed staff payout outer transaction", "Staff Payout workflow", canonical),
        "scripts/bootstrap_disposable_mysql_schema.py": ("validation", "disposable validation schema bootstrap", "test and validation operator", restricted),
        "scripts/migrate_legacy_ui_dataset.py": ("global_migration", "versioned legacy UI dataset migration", "reviewed migration operator", restricted),
        "scripts/plan_legacy_ui_dataset_integration.py": ("global_migration", "read-only migration planning boundary", "reviewed migration operator", restricted),
        "scripts/rebuild_legacy_ui_dataset_projections.py": ("global_migration", "restricted projection rebuild transaction", "reviewed migration operator", restricted),
        "scripts/run_case_import_invalid_scenario.py": ("validation", "disposable Case Import scenario transaction", "validation operator", restricted),
        "scripts/run_knowledge_worker.py": ("knowledge_retrieval", "knowledge worker heartbeat transaction", "knowledge worker operator", restricted),
        "scripts/run_line_worker.py": ("line_operations", "LINE worker heartbeat transaction", "LINE worker operator", restricted),
        "scripts/run_service_monitor.py": ("global_operations", "runtime monitor cycle transaction", "service monitor operator", restricted),
        "scripts/seed_contract_signing_line_identities.py": ("validation", "contract-signing validation seed transaction", "validation operator", restricted),
        "scripts/seed_contract_signing_roots.py": ("validation", "contract-signing validation seed transaction", "validation operator", restricted),
        "scripts/seed_validation_beclass_review.py": ("validation", "Case Import validation seed transaction", "validation operator", restricted),
        "scripts/verify_contract_signing_normal_chain.py": ("validation", "read-only contract-signing verifier", "validation operator", restricted),
        "scripts/verify_contract_signing_preconversion_isolation.py": ("validation", "read-only preconversion verifier", "validation operator", restricted),
        "scripts/verify_integrated_ui_validation_dataset.py": ("validation", "read-only integrated dataset verifier", "validation operator", restricted),
        "subsystems/anomalies/hcm_import_review_outbox_consumer.py": ("anomalies", "HCM review outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/client_finance/over_refund_recovery_matching_workflow.py": ("client_finance", "typed recovery-matching outer transaction", "Client Finance recovery-matching API", canonical),
        "subsystems/client_finance/over_refund_recovery_workflow.py": ("client_finance", "typed recovery outer transaction", "Client Finance recovery API", canonical),
        "subsystems/case_import/hcm_import_review_intake.py": ("case_import", "typed HCM review intake transaction", "HCM historical import adapter", canonical),
        "subsystems/case_import/staff_historical_adoption.py": ("case_import", "typed Staff historical adoption transaction", "Staff historical import adapter", canonical),
        "subsystems/contract_signing/client_contract_application.py": ("contract_signing", "typed client-contract outer transaction", "Contract Signing client API", canonical),
        "subsystems/contract_signing/command_receipts.py": ("contract_signing", "caller-owned contract receipt and outbox transaction", "Contract Signing applications", canonical),
        "subsystems/contract_signing/staff_contract_application.py": ("contract_signing", "typed staff-contract outer transaction", "Contract Signing staff API", canonical),
        "subsystems/customer_service/application.py": ("customer_service", "typed Customer Service outer transaction", "Customer Service API and LINE Service Help", canonical),
        "subsystems/government_subsidy/overpayment_workflow.py": ("government_subsidy", "typed overpayment outer transaction", "Government Subsidy overpayment API", canonical),
        "subsystems/government_subsidy/payer_master_workflow.py": ("government_subsidy", "typed payer-master outer transaction", "Government payer-master API", canonical),
        "subsystems/knowledge_retrieval/application.py": ("knowledge_retrieval", "typed Knowledge Retrieval application or worker transaction", "Knowledge API and worker", canonical),
        "subsystems/line/configuration_application.py": ("line_integration", "typed LINE configuration transaction", "LINE configuration API", canonical),
        "subsystems/line/delivery_admin_application.py": ("line_delivery", "typed delivery administration transaction", "LINE delivery admin API", canonical),
        "subsystems/line/delivery_worker.py": ("line_delivery", "worker claim and attempt transaction", "LINE delivery worker", restricted),
        "subsystems/line/identity_application.py": ("line_identity", "typed identity binding outer transaction", "LINE identity API and ingress", canonical),
        "subsystems/line/identity_management_application.py": ("line_identity", "typed identity management transaction", "LINE identity management API", canonical),
        "subsystems/line/identity_review_application.py": ("line_identity", "typed identity review transaction", "LINE identity review API", canonical),
        "subsystems/line/identity_revocation_worker.py": ("line_identity", "worker revocation claim transaction", "LINE identity revocation worker", restricted),
        "subsystems/line/media_application.py": ("line_media", "media archive worker transaction", "LINE media archive worker", restricted),
        "subsystems/line/order_group_application.py": ("line_order_group", "order-group query transaction", "LINE order-group API", restricted),
        "subsystems/line/rich_menu_application.py": ("line_rich_menu", "typed Rich Menu queue transaction", "LINE Rich Menu API", canonical),
        "subsystems/line/rich_menu_binding.py": ("line_rich_menu", "Rich Menu binding worker transaction", "LINE Rich Menu binding worker", restricted),
        "subsystems/line/rich_menu_worker.py": ("line_rich_menu", "Rich Menu publication worker transaction", "LINE Rich Menu worker", restricted),
        "subsystems/line/webhook_event_consumer.py": ("line_ingress", "webhook inbox claim and consume transaction", "LINE webhook worker", restricted),
        "subsystems/line/webhook_intake.py": ("line_ingress", "typed webhook intake transaction", "LINE webhook route", canonical),
        "subsystems/scheduling/customer_service_ticket_service.py": ("customer_service", "legacy customer-service compatibility transaction", "legacy Customer Service routes", "retain_restricted:canonical CustomerServiceApplication exists; migration requires a separate approved package"),
        "subsystems/scheduling/matching_notification_application.py": ("scheduling", "typed matching notification outer transaction", "Matching notification API and LINE callbacks", canonical),
        "subsystems/staff_payables/overpayment_recovery.py": ("staff_payables", "typed recovery outer transaction", "Staff Payables recovery API", canonical),
        "subsystems/staff_payables/overpayment_recovery_matching.py": ("staff_payables", "typed recovery-matching outer transaction", "Staff Payables recovery-matching API", canonical),
        "subsystems/validation_dataset/staff_master_source.py": ("validation", "validation dataset source transaction", "integrated validation dataset builder", restricted),
    }


def _provisional_registration_review() -> tuple[str, str, str, str]:
    return (
        "case_import",
        "typed provisional-registration Apply transaction",
        "line.line_bot.line_register",
        "retain_canonical:ProvisionalRegistrationApplication owns replay and conflict-safe client/beclass creation",
    )


def _legacy_line_bot_review(symbol: str) -> tuple[str, str, str, str]:
    replacements = {
        "_create_onboarding_tasks": "subsystems.line.delivery_task_workflow.enqueue_line_task",
        "ensure_order_for_case_no": "subsystems.line.identity_review_workflow._ensure_order_for_case_no",
        "line_bind": "subsystems.line.client_binding_application.bind_client",
        "line_register": "subsystems.case_import.provisional_registration_application",
        "line_webhook": "subsystems.line.webhook_inbox, user_lifecycle, identity_review_workflow, and delivery_task_workflow",
        "set_line_user_role": "subsystems.line.user_lifecycle.apply_role",
    }
    if symbol == "line_webhook":
        return (
            "line_ingress",
            "typed LINE ingress outer transaction",
            "api/main.py mounts line.line_bot.router",
            f"retain_canonical:{replacements[symbol]}",
        )
    replacement = replacements.get(symbol)
    if replacement is None:
        return _needs_decision_review("line/line_bot.py")
    return (
        "line_integration",
        "LINE transport route",
        "api/main.py mounts line.line_bot.router",
        f"retain_canonical:{replacement}",
    )


def _line_worker_review() -> tuple[str, str, str, str]:
    return (
        "line_delivery",
        "worker-owned claim, retry, or delivery-result transaction",
        "api/main.py lifespan starts line.worker",
        "retain_restricted:operational lease and attempt state is the current executor boundary",
    )


def _typed_line_review(path: str) -> tuple[str, str, str, str]:
    metadata = {
        "subsystems/line/delivery_task_admin_query.py": ("line_delivery", "typed task transition transaction", "api/routes/line_tasks.py", "retain_canonical:state-guarded task transition"),
        "subsystems/line/delivery_task_workflow.py": ("line_delivery", "caller-owned typed task enqueue transaction", "identity-review and rich-menu workflows", "retain_canonical:idempotent line_tasks enqueue"),
        "subsystems/line/identity_review_workflow.py": ("line_identity", "typed identity review transaction", "api/routes/line_reviews.py", "retain_canonical:Line identity review owner"),
        "subsystems/line/client_binding_application.py": ("line_identity", "typed client binding transaction", "line.line_bot.line_bind", "retain_canonical:client binding and rebind decision owner"),
        "subsystems/line/user_lifecycle.py": ("line_identity", "caller-owned LINE user lifecycle transaction", "line.line_bot webhook and role route", "retain_canonical:follow-unfollow-role-onboarding owner"),
        "subsystems/line/media_archive.py": ("line_media", "media metadata transaction", "rich-menu management workflow", "retain_canonical:controlled soft-delete and archive metadata"),
        "subsystems/line/rich_menu_publication_workflow.py": ("line_rich_menu", "typed rich-menu publication state-machine transaction", "line rich-menu routes and worker", "retain_canonical:publication lifecycle owner"),
        "subsystems/line/webhook_inbox.py": ("line_ingress", "caller-owned idempotent webhook-inbox transaction", "typed LINE ingress workflow", "retain_canonical:webhook inbox owner"),
        "subsystems/case_import/provisional_registration_application.py": ("case_import", "typed provisional-registration Apply transaction", "line.line_bot.line_register", "retain_canonical:single active registration with replay/conflict receipt"),
    }
    return metadata.get(path) or _needs_decision_review(path)


def _service_review(path: str) -> tuple[str, str, str, str]:
    metadata = {
        "services/anomaly_alert_detection.py": ("anomalies", "legacy reminder scan transaction", "test-only direct caller", "retain_restricted:dynamic statement is SELECT-only"),
        "services/finance_import_application.py": ("finance_import", "retired legacy workbook-import transaction", "no production caller after CLI test-adapter migration", "migrate_then_remove:scripts/imports/import_finance_excel.py uses typed ingestion"),
        "services/finance_import_reprocessing.py": ("finance_import", "retired legacy reprocess transaction", "no production apply caller; CLI rejects --apply", "migrate_then_remove:typed Historical Reprocess API is the replacement"),
        "services/system_alert_service.py": ("anomalies", "legacy operational alert projection transaction", "legacy finance-import application", "migrate_then_remove:subsystems.anomalies.system_alert_projection"),
    }
    return metadata.get(path) or _needs_decision_review(path)


def _needs_decision_review(path: str) -> tuple[str, str, str, str]:
    return (
        "owner_review_required",
        "unclassified writer boundary; no automatic owner assignment",
        f"manual review required for {path}",
        "needs_decision:merge-introduced writer requires explicit owner, caller, and transaction-boundary review",
    )


def _disposition(candidate: dict[str, object]) -> dict[str, object]:
    owner, boundary, caller, evidence = _review(candidate)
    disposition, replacement = evidence.split(":", 1)
    return {
        "identity": candidate["identity"], "fingerprint": candidate["fingerprint"],
        "owner": owner, "transaction_boundary": boundary, "runtime_caller": caller,
        "replacement_evidence": replacement, "final_disposition": disposition,
        "approved_to_remove": False,
    }


def _write_records(records: list[dict[str, object]]) -> None:
    rendered = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    RECORDS.write_text(rendered, encoding="utf-8")


def _write_manifest(records: list[dict[str, object]], candidates: list[dict[str, object]]) -> None:
    candidate_ids = {str(record["identity"]) for record in candidates}
    payload = {
        "contract": "production-writer-inventory/v3-disposition",
        "candidate_contract": "production-writer-inventory/v3-candidate",
        "candidate_evidence_sha256": sha256(CANDIDATE.read_bytes()).hexdigest(),
        "candidate_unique_identity_count": len(candidate_ids), "record_count": len(records),
        "covered_candidate_unresolved_count": sum(record["unresolved_reason"] == "owner_not_deterministic_from_path" for record in candidates),
        "covered_candidate_migrate_then_remove_count": sum(record["recommendation_candidate"] == "migrate_then_remove_candidate" for record in candidates),
        "approved_to_remove_count": 0,
        "final_disposition_counts": dict(sorted(Counter(str(record["final_disposition"]) for record in records).items())),
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    candidates = _load(CANDIDATE)
    existing = {str(record["identity"]): record for record in _load(RECORDS)}
    records = []
    reviewed_identities: set[str] = set()
    for candidate in candidates:
        identity = str(candidate["identity"])
        if identity in reviewed_identities:
            continue
        reviewed_identities.add(identity)
        if (
            identity not in existing
            or existing[identity].get("final_disposition") == "needs_decision"
            or str(candidate["relative_path"]) in REVIEW_REFRESH_PATHS
            or str(candidate["relative_path"]) in EXACT_SOURCE_REVIEWS
            or str(candidate["relative_path"]) in EXACT_SOURCE_RESTRICTED_REVIEWS
            or identity.startswith(("services/", "line/line_bot.py:"))
        ):
            existing[identity] = _disposition(candidate)
        records.append(existing[identity])
    records.sort(key=lambda record: str(record["identity"]))
    _write_records(records)
    _write_manifest(records, candidates)
    print(f"writer_inventory_v3_disposition records={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
