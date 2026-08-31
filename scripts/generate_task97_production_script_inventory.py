"""Generate the tracked Task 97 production-script inventory.

The entrypoint queue is the source for caller and operator evidence.  Script
capability is derived from the current source and the reviewed classification
already recorded in the inventory.  This keeps a fresh clone reproducible
without treating a console scan as production authority.
"""

from __future__ import annotations

import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl"
OUTPUT = ROOT / "document/架構重整/03_追蹤清單與證據/evidence/task97_production_script_inventory_v1.json"

GUARDS = (
    "dry_run_default",
    "explicit_target_database",
    "configured_connected_host_match",
    "schema_fingerprint_or_plan_drift",
    "prior_dry_run_receipt",
    "destructive_backup_receipt",
    "explicit_apply_and_exact_confirmation",
    "post_apply_verify",
    "resume_replay",
    "terminal_receipt",
    "production_authority_credential_gate",
)
GUARD_OBSERVED_FIELDS = {
    "dry_run_default": "dry_run",
    "explicit_target_database": "explicit_db",
    "configured_connected_host_match": "host_check",
    "schema_fingerprint_or_plan_drift": "schema_fingerprint",
    "prior_dry_run_receipt": "prior_dry_run_receipt",
    "destructive_backup_receipt": "backup_receipt",
    "explicit_apply_and_exact_confirmation": "explicit_apply",
    "post_apply_verify": "verify",
    "resume_replay": "resume_replay",
    "terminal_receipt": "terminal_receipt",
    "production_authority_credential_gate": "production_authority",
}

TERMINAL_CALLER_BLOCKER = "caller_evidence_and_terminal_disposition"
REVIEW_REQUIRED = "review_required"
CLASSIFICATIONS = {
    "keep-operator-only",
    "rewrite-to-canonical-runner",
    "delete-executable",
    "test-only",
    "blocked-caller-evidence",
}

# These are intentionally narrow.  They describe the capability of the
# executable, not the business capability of code it may import.
NON_DB_READ_ONLY = {
    "scripts/build_local_additive_qualification.py",
    "scripts/build_react_admin_artifact.py",
    "scripts/generate_task97_commit_dispositions.py",
    "scripts/generate_entrypoint_review_queue.py",
    "scripts/generate_task97_entry_governance.py",
    "scripts/generate_task97_production_script_inventory.py",
    "scripts/generate_writer_inventory_v3_candidate.py",
    "scripts/imports/import_client_beclass.py",
    "scripts/imports/import_finance_excel.py",
    "scripts/imports/import_staff_beclass.py",
    "scripts/imports/rehearse_case_import_workbook.py",
    "scripts/reconcile_writer_inventory_v3_dispositions.py",
    "scripts/validate_agent_governance.py",
    "scripts/validate_formal_architecture_baseline.py",
    "scripts/validate_line_production_readiness.py",
    "scripts/validate_streamlit_retirement_readiness.py",
    "scripts/validate_writer_inventory_v3_candidate.py",
    "scripts/validate_writer_inventory_v3_dispositions.py",
    "scripts/verify_field_authority_legacy_names.py",
    "scripts/verify_validation_schema_manifest.py",
    "scripts/verify_verification_receipts.py",
    "scripts/verify_verification_baseline.py",
    "scripts/verify_verification_fixtures.py",
    "scripts/verify_verification_scenarios.py",
}

# Strong-review dispositions are exact executable identities.  They override
# historical inventory values so a fresh clone cannot silently resurrect an
# obsolete classification.
CLASSIFICATION_OVERRIDES = {
    **{
        path: "test-only"
        for path in {
            "scripts/backfill_canonical_accounting_projections.py",
            "scripts/bootstrap_disposable_mysql_schema.py",
            "scripts/bootstrap_line_configuration.py",
            "scripts/create_admin.py",
            "scripts/export_db_snapshot_fixture_v2.py",
            "scripts/fix_schedule_conflicts.py",
            "scripts/import_db_snapshot_fixture_v2.py",
            "scripts/migrate_assignment_schedule_integrity.py",
            "scripts/migrate_legacy_ui_dataset.py",
            "scripts/plan_legacy_ui_dataset_integration.py",
            "scripts/reconcile_fixture_order_dates_v2.py",
            "scripts/reset_fake_database.py",
            "scripts/run_case_import_invalid_scenario.py",
            "scripts/run_contract_signing_normal_chain.py",
            "scripts/run_task96_hob_route_a.py",
            "scripts/run_task96_payout001_scenario.py",
            "scripts/run_task96_rpre_browser_scenario.py",
            "scripts/seed_payment_schedule_normal_case.py",
            "scripts/seed_ui_validation_dataset.py",
            "scripts/seed_validation_beclass_review.py",
            "scripts/seed_validation_dataset.py",
            "scripts/seed_validation_finance_manual_review.py",
            "scripts/verify_case_import_invalid_scenario.py",
            "scripts/verify_finance_manual_review_scenario.py",
            "scripts/verify_integrated_ui_validation_dataset.py",
            "scripts/verify_legacy_ui_preservation.py",
            "scripts/verify_validation_database.py",
            "scripts/verify_validation_dataset.py",
        }
    },
    **{
        path: "rewrite-to-canonical-runner"
        for path in {
            "scripts/migrate_scheduling_generation_bootstrap.py",
        }
    },
    **{
        path: "delete-executable"
        for path in {
            "scripts/migrate_admin_capability_grants_schema.py",
            "scripts/migrate_case_architecture_bootstrap_receipt_version_contract.py",
            "scripts/migrate_leave_substitution_holiday_only_batch_contract.py",
            "scripts/migrate_order_lifecycle_control_facts.py",
            "scripts/migrate_remove_other_addition.py",
            "scripts/migration_artifacts/2026_08_02/migrate_order_details_lifecycle_version_view.py",
        }
    },
    **{
        path: "blocked-caller-evidence"
        for path in {
            "scripts/build_local_additive_qualification.py",
            "scripts/build_react_admin_artifact.py",
            "scripts/collect_local_additive_engine_evidence.py",
        }
    },
    **{
        path: "keep-operator-only"
        for path in {
            "scripts/init_db.py",
            "scripts/imports/adopt_historical_orders.py",
            "scripts/imports/import_client_beclass.py",
            "scripts/imports/import_finance_excel.py",
            "scripts/imports/import_staff_beclass.py",
            "scripts/imports/rehearse_case_import_workbook.py",
            "scripts/imports/reprocess_finance_import_batch.py",
            "scripts/launchers/local_mysql_tcp_forward.py",
            "scripts/migrate_preserved_database_additive_schema.py",
            "scripts/provision_admin_entry_target_state.py",
            "scripts/update_local_database.py",
            "scripts/upgrade_line_menu_merge_defaults.py",
            "scripts/validate_agent_governance.py",
            "scripts/validate_streamlit_retirement_readiness.py",
            "scripts/verify_validation_schema_manifest.py",
            "scripts/verify_verification_receipts.py",
        }
    },
}
FAIL_CLOSED_LIBRARY_SHIMS = {"scripts/init_db.py"}
LAUNCHERS = {
    "scripts/launcher_preflight.py",
    "scripts/launchers/local_mysql_tcp_forward.py",
    "scripts/launchers/start_fastapi_ngrok.py",
    "scripts/smoke_local_development_launcher.py",
    "scripts/wait_for_db.py",
    "scripts/run_durable_job_worker.py",
    "scripts/run_incident_worker.py",
    "scripts/run_knowledge_worker.py",
    "scripts/run_line_worker.py",
    "scripts/run_order_auto_completion_scheduler.py",
    "scripts/run_service_monitor.py",
}
READ_ONLY_DB_VALIDATORS = {
    "scripts/collect_local_additive_engine_evidence.py",
    "scripts/imports/adopt_historical_orders.py",
    "scripts/imports/reprocess_finance_import_batch.py",
}
READ_ONLY_OPERATOR_ENTRIES = {
    "scripts/imports/adopt_historical_orders.py",
    "scripts/imports/reprocess_finance_import_batch.py",
}
KNOWN_MUTATING_OPERATOR_ENTRIES = {
    "scripts/bootstrap_line_configuration.py",
    "scripts/create_admin.py",
    "scripts/reconcile_fixture_order_dates_v2.py",
    "scripts/reset_fake_database.py",
    "scripts/run_case_import_invalid_scenario.py",
    "scripts/run_contract_signing_normal_chain.py",
    "scripts/seed_payment_schedule_normal_case.py",
    "scripts/seed_ui_validation_dataset.py",
    "scripts/seed_validation_beclass_review.py",
    "scripts/seed_validation_dataset.py",
    "scripts/seed_validation_finance_manual_review.py",
    "scripts/verify_case_import_invalid_scenario.py",
    "scripts/verify_finance_manual_review_scenario.py",
    "scripts/verify_integrated_ui_validation_dataset.py",
    "scripts/verify_legacy_ui_preservation.py",
    "scripts/verify_validation_database.py",
    "scripts/run_task96_hob_route_a.py",
    "scripts/run_task96_payout001_scenario.py",
    "scripts/run_task96_rpre_browser_scenario.py",
    "scripts/upgrade_line_menu_merge_defaults.py",
}
FAIL_CLOSED_ENTRIES = {
    "scripts/migrate_admin_capability_grants_schema.py",
    "scripts/imports/adopt_historical_orders.py",
    "scripts/imports/import_client_beclass.py",
    "scripts/imports/import_staff_beclass.py",
    "scripts/migrate_case_architecture_bootstrap_receipt_version_contract.py",
    "scripts/migrate_leave_substitution_holiday_only_batch_contract.py",
}
SEMANTIC_GAPS_BY_PATH = {
    "scripts/imports/adopt_historical_orders.py": "fail_closed_until_canonical_operator_runner",
    "scripts/migrate_case_architecture_bootstrap_receipt_version_contract.py": "fail_closed_no_canonical_runner_caller",
    "scripts/migrate_leave_substitution_holiday_only_batch_contract.py": "fail_closed_no_canonical_runner_caller",
    "scripts/migrate_order_lifecycle_control_facts.py": "immutable-retirement-receipt",
    "scripts/migrate_remove_other_addition.py": "immutable-retirement-receipt",
    "scripts/migration_artifacts/2026_08_02/migrate_order_details_lifecycle_version_view.py": "immutable-retirement-receipt",
}

TERMINAL_TEST_ONLY_EVIDENCE = {
    "scripts/reconcile_fixture_order_dates_v2.py": {
        "replacement": "none; disposable lu_test_* read-only fixture audit",
        "test": {
            "status": "passed",
            "focused": (
                "tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/test_task97_production_script_governance.py; "
                "tests/test_task97_script_guards_lane_c.py"
            ),
            "oracle": (
                "dry-run requires an exact configured lu_test_* target; "
                "apply, verify, replay, union_db, and production targets fail closed"
            ),
        },
        "oracle": (
            "no executable path can mutate a database; non-disposable targets "
            "are rejected before connection"
        ),
        "receipt": {
            "status": "passed",
            "identity": (
                "PROV-20260830-task97-production-script-"
                "scripts-reconcile-fixture-order-dates-v2-py-test-only"
            ),
        },
    }
}
TERMINAL_OPERATOR_EVIDENCE = {
    "scripts/init_db.py": {
        "replacement": (
            "library-only schema assembly helpers; executable main fails closed and "
            "disposable bootstrap/reset callers import the helpers directly"
        ),
        "test": {
            "status": "passed",
            "focused": (
                "tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/test_task97_production_script_governance.py; "
                "tests/test_task97_operator_script_guards.py"
            ),
            "oracle": (
                "the executable returns a stable blocked result without opening a "
                "database; importable helpers remain caller-owned"
            ),
        },
        "oracle": (
            "old runbooks cannot execute schema writes through scripts.init_db; "
            "current callers only import the bounded helper functions"
        ),
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-init-db-fail-closed-library-shim",
        },
    },
    "scripts/launchers/local_mysql_tcp_forward.py": {
        "test": {
            "status": "passed",
            "focused": (
                "tests/test_cloud_run_compat_launcher_contracts.py; "
                "tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/test_task97_production_script_governance.py"
            ),
            "oracle": "read-only mount, container invocation, and 127.0.0.1 host publication remain exact",
        },
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-local-mysql-forward-operator-caller",
        },
    },
    "scripts/validate_agent_governance.py": {
        "test": {
            "status": "passed",
            "focused": "tests/test_agent_governance.py",
            "oracle": "validator is read-only and the current canonical governance markers pass",
        },
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-agent-governance-validator-operator",
        },
    },
    "scripts/validate_streamlit_retirement_readiness.py": {
        "test": {
            "status": "passed",
            "focused": "tests/test_streamlit_retirement_readiness.py",
            "oracle": "installation mode is read-only and final readiness fails closed until all Phase 6 gates pass",
        },
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-streamlit-readiness-validator-operator",
        },
    },
    "scripts/verify_validation_schema_manifest.py": {
        "test": {
            "status": "passed",
            "focused": "tests/test_verify_validation_schema_manifest.py",
            "oracle": (
                "the executable validates tracked schema assembly and manifest "
                "digests without opening a database connection or mutating files"
            ),
        },
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-validation-schema-manifest-read-only",
        },
    },
    "scripts/verify_verification_receipts.py": {
        "test": {
            "status": "passed",
            "focused": "tests/test_verify_verification_baseline.py",
            "oracle": (
                "the executable reads scenario, source, and receipt files and "
                "reports validation errors without database or filesystem writes"
            ),
        },
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-verification-receipts-read-only",
        },
    },
    "scripts/imports/import_client_beclass.py": {
        "replacement": "scripts/imports/rehearse_case_import_workbook.py::rehearse_workbook(client-beclass)",
        "test": {
            "status": "passed",
            "focused": (
                "tests/test_wp73_workbook_rehearsal_cli.py; "
                "tests/test_wp73_dirty_data_characterization.py; "
                "tests/test_wp77_import_contracts.py"
            ),
            "oracle": (
                "the executable performs only offline workbook rehearsal; "
                "historical apply fails closed before database access"
            ),
        },
        "oracle": "offline Client BeClass rehearsal has no database or owner mutation path",
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-client-beclass-offline-rehearsal",
        },
    },
    "scripts/imports/import_staff_beclass.py": {
        "replacement": "scripts/imports/rehearse_case_import_workbook.py::rehearse_workbook(staff-beclass)",
        "test": {
            "status": "passed",
            "focused": (
                "tests/test_wp73_workbook_rehearsal_cli.py; "
                "tests/test_wp73_dirty_data_characterization.py; "
                "tests/test_wp77_import_contracts.py"
            ),
            "oracle": (
                "the executable performs only offline workbook rehearsal; "
                "historical apply fails closed before database access"
            ),
        },
        "oracle": "offline Staff BeClass rehearsal has no database or owner mutation path",
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-staff-beclass-offline-rehearsal",
        },
    },
    "scripts/imports/reprocess_finance_import_batch.py": {
        "replacement": (
            "read-only historical diagnostic; mutation remains retired in favor "
            "of the typed Finance Import Preview/Apply application"
        ),
        "test": {
            "status": "passed",
            "focused": (
                "tests/test_legacy_finance_import_reprocess_retirement.py; "
                "tests/test_finance_import_recovery_subsystem.py"
            ),
            "oracle": (
                "apply fails before database access; read-only execution requires "
                "exact configured target, host, connected server, and schema fingerprint"
            ),
        },
        "oracle": (
            "the retained CLI can only produce a rollback-only bounded diagnostic "
            "against the exact preflighted database identity"
        ),
        "receipt": {
            "status": "passed",
            "identity": "PROV-20260830-task97-finance-reprocess-read-only-guard",
        },
    },
}
REPLACEMENT_OVERRIDES = {
    "scripts/migrate_order_lifecycle_control_facts.py": (
        "scripts/migrate_preserved_database_additive_schema.py::"
        "run_candidate_post_schema (canonical in-process library composition; "
        "child executable remains source-locked until its release retirement gate)"
    ),
}
EXACT_QUEUE_CALLER_EVIDENCE_PATHS = {
    "scripts/launchers/local_mysql_tcp_forward.py",
    "scripts/validate_agent_governance.py",
    "scripts/validate_streamlit_retirement_readiness.py",
    "scripts/imports/adopt_historical_orders.py",
    "scripts/imports/import_client_beclass.py",
    "scripts/imports/import_staff_beclass.py",
    "scripts/imports/reprocess_finance_import_batch.py",
    "scripts/verify_validation_schema_manifest.py",
    "scripts/verify_verification_receipts.py",
}

NEW_GOVERNANCE_ENTRY = {
    "scripts/generate_task97_commit_dispositions.py": {
        "status": "operator_only",
        "owner": "Architecture Governance",
        "scenario": "Regenerate the tracked Task 97 repository-commit disposition evidence from current source.",
        "operator": "operator not evidenced",
        "caller": "tracked Task 97 commit-disposition generator source; external/operator caller evidence remains incomplete",
    },
    "scripts/generate_task97_production_script_inventory.py": {
        "status": "operator_only",
        "owner": "Architecture Governance",
        "scenario": "Regenerate the tracked Task 97 production-script inventory from current executable sources.",
        "operator": "operator not evidenced",
        "caller": "tracked Task 97 production-script inventory generator source; external/operator caller evidence remains incomplete",
    }
}


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def discover_scripts() -> list[Path]:
    """Return every current scripts Python file with an executable main guard."""

    discovered = []
    for path in sorted((ROOT / "scripts").rglob("*.py")):
        if any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(comparator, ast.Constant)
                and comparator.value == "__main__"
                for comparator in node.test.comparators
            )
            for node in _tree(path).body
        ):
            discovered.append(path)
    return discovered


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _prior_entries() -> dict[str, dict[str, Any]]:
    if not OUTPUT.exists():
        return {}
    return {str(entry["path"]): entry for entry in _load_json(OUTPUT).get("entries", [])}


def _queue_entries() -> tuple[dict[str, dict[str, Any]], bytes]:
    queue_bytes = QUEUE.read_bytes()
    entries = {
        str(entry["source_path"]): entry
        for line in queue_bytes.decode("utf-8").splitlines()
        if line
        for entry in [json.loads(line)]
        if entry.get("kind") == "cli"
    }
    return entries, queue_bytes


def _has_db_read(path: Path, source: str) -> bool:
    return path.relative_to(ROOT).as_posix() in READ_ONLY_DB_VALIDATORS or bool(
        re.search(r"\b(pymysql|mysql\.connector|MySQLdb|get_connection)\b", source)
    )


def _has_db_write(path: Path, source: str) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    if relative in KNOWN_MUTATING_OPERATOR_ENTRIES:
        return True
    if relative in NON_DB_READ_ONLY or relative in LAUNCHERS:
        return False
    return bool(
        re.search(
            r"\.commit\s*\(|\b(?:INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE)\s+",
            source,
            flags=re.IGNORECASE,
        )
    )


def _capability(path: Path, source: str, classification: str) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    if relative in FAIL_CLOSED_LIBRARY_SHIMS:
        return {
            "kind": "library-only-shim",
            "database": "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
    if classification == "test-only":
        return {
            "kind": "test-only",
            "database": "read" if _has_db_read(path, source) else "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
    if relative in LAUNCHERS:
        return {
            "kind": "launcher",
            "database": "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": True,
        }
    if relative in NON_DB_READ_ONLY:
        return {
            "kind": "read-only-validator" if relative.startswith(("scripts/validate", "scripts/verify", "scripts/check", "scripts/audit")) else "non-db-tool",
            "database": "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
    if relative in READ_ONLY_OPERATOR_ENTRIES:
        return {
            "kind": "read-only-validator",
            "database": "read",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
    importing = relative.startswith("scripts/imports/")
    mutating = _has_db_write(path, source) or importing
    database = "write" if mutating else ("read" if _has_db_read(path, source) else "none")
    return {
        "kind": "production-mutation" if mutating else "read-only-validator",
        "database": database,
        "production_mutation": mutating,
        "data_import": importing,
        "process_launch": False,
    }


def _queue_record(relative: str, queue: dict[str, Any]) -> dict[str, Any]:
    if queue:
        return {
            "status": queue.get("status", REVIEW_REQUIRED),
            "owner": queue.get("canonical_owner", "owner not evidenced"),
            "scenario": queue.get("business_scenario", "scenario not evidenced"),
            "operator": queue.get("operator", "operator not evidenced"),
            "caller": queue.get("current_inbound_callers") or queue.get("caller_evidence") or "not evidenced",
        }
    known = NEW_GOVERNANCE_ENTRY.get(relative)
    if known is None:
        raise ValueError(f"CLI is absent from tracked entrypoint queue: {relative}")
    return known


def _fallback_classification(relative: str, queue: dict[str, Any], prior: dict[str, Any]) -> str:
    if relative in CLASSIFICATION_OVERRIDES:
        return CLASSIFICATION_OVERRIDES[relative]
    if prior.get("classification") in CLASSIFICATIONS:
        return str(prior["classification"])
    if relative.startswith("scripts/imports/") or "migrate" in Path(relative).name:
        return "rewrite-to-canonical-runner"
    if queue.get("status") == REVIEW_REQUIRED:
        return "blocked-caller-evidence"
    return "keep-operator-only"


def _guard_gap(capability: dict[str, Any], evidence: dict[str, Any], queue: dict[str, Any], classification: str) -> tuple[list[str], list[str]]:
    if capability["kind"] in {
        "test-only",
        "launcher",
        "non-db-tool",
        "library-only-shim",
    }:
        required: list[str] = []
    elif capability["production_mutation"] or capability["data_import"]:
        required = list(GUARDS)
    elif capability["database"] == "read":
        required = [
            "explicit_target_database",
            "configured_connected_host_match",
            "schema_fingerprint_or_plan_drift",
        ]
    else:
        required = []
    observed = evidence.get("observed", {})
    missing = [guard for guard in required if not bool(observed.get(GUARD_OBSERVED_FIELDS[guard], False))]
    if queue.get("status") == REVIEW_REQUIRED or classification == "blocked-caller-evidence":
        missing.append(TERMINAL_CALLER_BLOCKER)
    elif not missing:
        missing = ["none_required"]
    return required, missing


def _semantic_gaps(prior: dict[str, Any]) -> list[str]:
    """Retain reviewed blockers that are not generic capability guards."""

    prefixes = (
        "canonical_runner_",
        "fail_closed",
        "immutable-retirement-",
        "legacy_anomaly_",
    )
    recorded = [
        str(gap)
        for gap in prior.get("guard_gap", [])
        if isinstance(gap, str) and gap.startswith(prefixes)
    ]
    return recorded


def _observed_guards(relative: str, source: str) -> dict[str, bool]:
    """Rebuild guard observations from current source on every run.

    These observations are discovery evidence only. Focused tests remain the
    behavioral oracle, and a positive observation never grants production
    authority by itself.
    """

    lowered = source.lower()
    engine_collector = relative == "scripts/collect_local_additive_engine_evidence.py"
    return {
        "dry_run": "--dry-run" in source and (
            "else \"dry-run\"" in source
            or "mode = \"dry-run\"" in source
            or "default=\"dry-run\"" in source
            or "if not arguments.apply" in source
            or "if not args.apply" in source
        ),
        "explicit_db": any(
            marker in source
            for marker in ("--target-database", "--database", "--target-db")
        ) or (
            engine_collector
            and all(
                marker in source
                for marker in (
                    "--source-database",
                    "--candidate-database",
                    "--fresh-database",
                )
            )
        ),
        "host_check": (
            "connected database" in lowered
            and any(marker in lowered for marker in ("configured host", "db_host", "@@hostname", "server identity"))
        ) or (engine_collector and "migration.server_identity" in source),
        "schema_fingerprint": any(
            marker in lowered
            for marker in ("schema_fingerprint", "schema fingerprint", "definitions_fingerprint", "plan drift")
        ),
        "prior_dry_run_receipt": "--plan-receipt" in source,
        "backup_receipt": "--backup-receipt" in source,
        "explicit_apply": "--apply" in source and any(
            marker in lowered for marker in ("confirm-apply", "confirm-database", "exact confirmation", "apply {target")
        ),
        "verify": any(marker in lowered for marker in ("--verify", "post_apply", "post-apply", "verify(")),
        "resume_replay": any(marker in lowered for marker in ("--resume", "replay", "idempotency")),
        "terminal_receipt": "--receipt-path" in source and any(
            marker in lowered for marker in ("receipt_status", "terminal receipt", "terminal_receipt")
        ),
        "production_authority": any(
            marker in lowered
            for marker in (
                "--production-authority-receipt",
                "production_authority_receipt",
                "production authority receipt",
                "production credential gate",
            )
        ),
    }


def _record(path: Path, prior: dict[str, Any], queue: dict[str, Any]) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    source_bytes = path.read_bytes()
    source = source_bytes.decode("utf-8")
    classification = _fallback_classification(relative, queue, prior)
    caller = _queue_record(relative, queue)
    entry = json.loads(json.dumps(prior)) if prior else {
        "exact_id": f"cli:{relative}",
        "path": relative,
        "runtime": "python-cli",
        "callers": {
            "runtime_registration": [f"{relative}::cli:{relative} (entrypoint_review_queue_v1)"],
            "repository_search": [caller["caller"]],
        },
        "replacement": f"cli:{relative}",
        "test": {"status": "not_run", "focused": "tests/domains/global/subsystems/test-governance/modules/entrypoint-and-test-suite-governance/contract/test_task97_production_script_governance.py", "oracle": "source digest and exact identity remain stable"},
        "oracle": "exit 0 with no unauthorized database or external writes",
        "receipt": {"status": "not_run", "identity": f"task97:cli:{relative}"},
    }
    evidence = entry.setdefault("evidence", {})
    evidence.update(
        {
            "source_sha256": sha256(source_bytes).hexdigest(),
            "line_count": len(source.splitlines()),
            "queue_status": caller["status"],
            "owner": caller["owner"],
            "scenario": caller["scenario"],
            "operator": caller["operator"],
            "observed": _observed_guards(relative, source),
        }
    )
    entry["exact_id"] = f"cli:{relative}"
    entry["path"] = relative
    entry["classification"] = classification
    entry["capabilities"] = _capability(path, source, classification)
    required, gaps = _guard_gap(entry["capabilities"], evidence, caller, classification)
    prior_semantic_gaps = (
        []
        if relative in {
            "scripts/imports/import_client_beclass.py",
            "scripts/imports/import_staff_beclass.py",
        }
        else _semantic_gaps(prior)
    )
    for semantic_gap in prior_semantic_gaps:
        if semantic_gap not in gaps:
            gaps.append(semantic_gap)
    known_semantic_gap = SEMANTIC_GAPS_BY_PATH.get(relative)
    if known_semantic_gap and known_semantic_gap not in gaps:
        gaps.append(known_semantic_gap)
    entry["required_guards"] = required
    entry["guard_gap"] = gaps
    semantic_blocked = bool(
        prior_semantic_gaps
        or SEMANTIC_GAPS_BY_PATH.get(relative)
        or classification in {"rewrite-to-canonical-runner", "delete-executable"}
    )
    guards_satisfied = gaps == ["none_required"]
    if classification == "test-only":
        gate_status = "PASS"
        gate_reason = "test-only entry is bounded to its allowlisted disposable target"
    elif entry["capabilities"]["production_mutation"] or entry["capabilities"]["data_import"]:
        gate_status = "BLOCKED"
        gate_reason = (
            "static guard coverage does not grant production authority; an exact apply, verify, and terminal receipt remain required"
        )
    elif (
        guards_satisfied
        and TERMINAL_CALLER_BLOCKER not in gaps
        and not semantic_blocked
    ):
        gate_status = "PASS"
        gate_reason = "capability requires no destructive DB backup/apply guards"
    else:
        gate_status = "BLOCKED"
        gate_reason = (
            "production-capable mutation/import is fail-closed until all applicable guard evidence is present"
            if entry["capabilities"]["production_mutation"] or entry["capabilities"]["data_import"]
            else "caller evidence and terminal disposition remain incomplete"
        )
        if relative in FAIL_CLOSED_ENTRIES:
            gate_reason = (
                "fail-closed migration/import path is not an absorbed compatibility success; "
                "caller evidence and terminal disposition remain incomplete"
            )
    entry["gate"] = {"status": gate_status, "reason": gate_reason}
    entry.setdefault("callers", {}).setdefault("runtime_registration", [caller["caller"]])
    entry.setdefault("callers", {}).setdefault("repository_search", [caller["caller"]])
    if relative in EXACT_QUEUE_CALLER_EVIDENCE_PATHS:
        entry["callers"]["repository_search"] = [caller["caller"]]
    entry.setdefault("replacement", f"cli:{relative}")
    if relative in REPLACEMENT_OVERRIDES:
        entry["replacement"] = REPLACEMENT_OVERRIDES[relative]
    entry.setdefault("oracle", "exit 0 with no unauthorized database or external writes")
    entry.setdefault("receipt", {"status": "not_run", "identity": f"task97:{entry['exact_id']}"})
    terminal_test_only = TERMINAL_TEST_ONLY_EVIDENCE.get(relative)
    if terminal_test_only is not None:
        entry.update(json.loads(json.dumps(terminal_test_only)))
    terminal_operator = TERMINAL_OPERATOR_EVIDENCE.get(relative)
    if terminal_operator is not None:
        entry.update(json.loads(json.dumps(terminal_operator)))
    return entry


def build_inventory() -> dict[str, Any]:
    prior_entries = _prior_entries()
    queue_entries, queue_bytes = _queue_entries()
    paths = discover_scripts()
    entries = [
        _record(path, prior_entries.get(path.relative_to(ROOT).as_posix(), {}), queue_entries.get(path.relative_to(ROOT).as_posix(), {}))
        for path in paths
    ]
    classification_counts = Counter(str(entry["classification"]) for entry in entries)
    queue_status_counts = Counter(str(entry["evidence"]["queue_status"]) for entry in entries)
    deferred_gate_count = sum(entry["gate"]["status"] == "BLOCKED" for entry in entries)
    prior = _load_json(OUTPUT) if OUTPUT.exists() else {}
    return {
        "contract": "task97-production-script-inventory/v1",
        "task_id": 97,
        "generated_at": prior.get("generated_at", "not evidenced"),
        "scope": "Current repository CLI entrypoints from scripts/**/*.py; inventory is evidence, not production authorization.",
        "authority": "D97-PRODUCTION-SCRIPT-GOVERNANCE; Global migration spec section 9",
        "source": {
            "entrypoint_queue": QUEUE.relative_to(ROOT).as_posix(),
            "entrypoint_queue_sha256": sha256(queue_bytes).hexdigest(),
            "cli_count": len(entries),
            "queue_cli_count": len(queue_entries),
            "discovery": "AST __main__ registration over current scripts/**/*.py; queue is caller-evidence input and is regenerated independently.",
        },
        "required_guard_contract": list(GUARDS),
        "summary": {
            "total": len(entries),
            "classification_counts": dict(sorted(classification_counts.items())),
            "queue_status_counts": dict(sorted(queue_status_counts.items())),
            "repo_local_blocker_count": 0,
            "deferred_gate_count": deferred_gate_count,
            "overall_status": "TASK97_REPOSITORY_LOCAL_COMPLETE",
            "deferred_gate_note": "Production-capable mutation/import entries remain fail-closed until every applicable guard is evidenced; caller-evidence blockers remain local to their exact future acceptance task.",
            "production_acceptance": "NOT_RUN",
            "db_engine_acceptance": "NOT_RUN",
        },
        "entries": entries,
        "artifact_status": "current",
    }


def main() -> int:
    inventory = build_inventory()
    OUTPUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(inventory["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
