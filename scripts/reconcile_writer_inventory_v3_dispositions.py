"""Apply reviewed dispositions to the immutable writer-inventory candidate."""

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
REVIEW_REFRESH_PATHS = frozenset(
    {"infrastructure/mysql/admin_capability_grant_repository.py"}
)


def _load(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _review(record: dict[str, object]) -> tuple[str, str, str, str]:
    path = str(record["relative_path"])
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
    return _service_review(path)


def _current_runtime_review(path: str) -> tuple[str, str, str, str] | None:
    metadata = {
        "infrastructure/mysql/admin_capability_grant_repository.py": (
            "access_control", "retired legacy capability-grant transaction",
            "no runtime caller; capability-grant routes return HTTP 410",
            "migrate_then_remove:equal business access no longer consumes per-user grants; physical schema retirement requires a separate approved migration",
        ),
        "infrastructure/mysql/anomaly_registry_repository.py": (
            "anomalies", "typed anomaly workflow transaction",
            "subsystems/anomalies/root_fact_projection_workflow.py", "retain_canonical:manual-review resolution event is owned by the canonical anomaly workflow",
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
        "subsystems/anomalies/client_over_refund_recovery_anomaly_consumer.py": ("anomalies", "Client Finance outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/anomalies/client_refund_underpayment_anomaly_consumer.py": ("anomalies", "Client Finance outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/anomalies/government_overpayment_anomaly_consumer.py": ("anomalies", "Government Subsidy outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/anomalies/staff_overpayment_recovery_anomaly_consumer.py": ("anomalies", "Staff Payables outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/anomalies/staff_payout_difference_anomaly_consumer.py": ("anomalies", "Staff Payables outbox projection delivery transaction", "Anomalies outbox worker", canonical),
        "subsystems/client_finance/over_refund_recovery_matching_workflow.py": ("client_finance", "typed recovery-matching outer transaction", "Client Finance recovery-matching API", canonical),
        "subsystems/client_finance/over_refund_recovery_workflow.py": ("client_finance", "typed recovery outer transaction", "Client Finance recovery API", canonical),
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
        "subsystems/scheduling/staff_leave_review_service.py": ("scheduling", "legacy leave-review direct transaction", "no canonical route; LINE leave request plan is pending", "migrate_then_remove:approved product direction requires a new Scheduling request workflow before this legacy drift can be removed"),
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
