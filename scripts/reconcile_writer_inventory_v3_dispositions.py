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


def _load(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _review(record: dict[str, object]) -> tuple[str, str, str, str]:
    path = str(record["relative_path"])
    reviewed = _current_runtime_review(path)
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
            "access_control", "typed capability-grant Apply transaction",
            "api/routes/capability_grants.py", "retain_canonical:grant event, session revocation, receipt, and authorization version share one Access Control transaction",
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
    return (
        "line_integration",
        "LINE transport route",
        "api/main.py mounts line.line_bot.router",
        f"retain_canonical:{replacements[symbol]}",
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
    return metadata[path]


def _service_review(path: str) -> tuple[str, str, str, str]:
    metadata = {
        "services/anomaly_alert_detection.py": ("anomalies", "legacy reminder scan transaction", "test-only direct caller", "retain_restricted:dynamic statement is SELECT-only"),
        "services/finance_import_application.py": ("finance_import", "retired legacy workbook-import transaction", "no production caller after CLI test-adapter migration", "migrate_then_remove:scripts/imports/import_finance_excel.py uses typed ingestion"),
        "services/finance_import_reprocessing.py": ("finance_import", "retired legacy reprocess transaction", "no production apply caller; CLI rejects --apply", "migrate_then_remove:typed Historical Reprocess API is the replacement"),
        "services/system_alert_service.py": ("anomalies", "legacy operational alert projection transaction", "legacy finance-import application", "migrate_then_remove:subsystems.anomalies.system_alert_projection"),
    }
    return metadata[path]


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
        if identity not in existing or identity.startswith(("services/", "line/line_bot.py:")):
            existing[identity] = _disposition(candidate)
        records.append(existing[identity])
    records.sort(key=lambda record: str(record["identity"]))
    _write_records(records)
    _write_manifest(records, candidates)
    print(f"writer_inventory_v3_disposition records={len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
