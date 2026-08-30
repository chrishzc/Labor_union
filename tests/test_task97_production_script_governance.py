"""Focused integrity checks for the Task 97 production-script evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.generate_task97_production_script_inventory import discover_scripts


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (
    ROOT
    / "document/架構重整/03_追蹤清單與證據/evidence/"
    / "task97_production_script_inventory_v1.json"
)

REQUIRED_ENTRY_FIELDS = {
    "exact_id",
    "path",
    "runtime",
    "callers",
    "evidence",
    "classification",
    "guard_gap",
    "replacement",
    "gate",
    "test",
    "oracle",
    "receipt",
}
EXPECTED_COUNTS = {
    "keep-operator-only": 37,
    "test-only": 38,
    "rewrite-to-canonical-runner": 2,
    "delete-executable": 6,
    "blocked-caller-evidence": 3,
}


def _load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_task97_script_inventory_is_complete_and_current() -> None:
    inventory = _load_inventory()
    entries = inventory["entries"]

    assert inventory["contract"] == "task97-production-script-inventory/v1"
    assert inventory["source"]["cli_count"] == len(discover_scripts()) == 86
    assert len(entries) == 86
    assert inventory["summary"]["total"] == 86
    assert inventory["source"]["queue_cli_count"] == 86

    identities = [entry["exact_id"] for entry in entries]
    paths = [entry["path"] for entry in entries]
    assert len(set(identities)) == 86
    assert len(set(paths)) == 86
    assert all(entry.keys() >= REQUIRED_ENTRY_FIELDS for entry in entries)

    observed_counts = {
        classification: sum(
            entry["classification"] == classification for entry in entries
        )
        for classification in EXPECTED_COUNTS
    }
    assert observed_counts == EXPECTED_COUNTS
    assert inventory["summary"]["classification_counts"] == observed_counts

    for entry in entries:
        source = ROOT / entry["path"]
        assert source.is_file(), entry["path"]
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert entry["evidence"]["source_sha256"] == digest
        assert entry["exact_id"] == f"cli:{entry['path']}"
        assert entry["callers"]["runtime_registration"]
        assert entry["callers"]["repository_search"]
        assert entry["replacement"]
        assert entry["guard_gap"]
        assert entry["oracle"]
        assert entry["receipt"]["identity"]
        assert entry["gate"]["status"] in {"PASS", "BLOCKED", "NOT_RUN"}
        if entry["capabilities"]["production_mutation"] or entry["capabilities"]["data_import"]:
            assert entry["gate"]["status"] == "BLOCKED"
            assert set(entry["required_guards"]) == set(inventory["required_guard_contract"])
        elif entry["capabilities"]["kind"] in {"launcher", "non-db-tool", "test-only"}:
            assert not {
                "prior_dry_run_receipt",
                "destructive_backup_receipt",
                "explicit_apply_and_exact_confirmation",
            }.intersection(entry["required_guards"])


def test_task97_script_inventory_preserves_guard_contract_and_blocked_callers() -> None:
    inventory = _load_inventory()
    required_guards = set(inventory["required_guard_contract"])
    assert required_guards == {
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
    }

    blocked = [
        entry
        for entry in inventory["entries"]
        if entry["classification"] == "blocked-caller-evidence"
    ]
    assert {entry["path"] for entry in blocked} == {
        "scripts/build_local_additive_qualification.py",
        "scripts/build_react_admin_artifact.py",
        "scripts/collect_local_additive_engine_evidence.py",
    }
    assert all(entry["evidence"]["queue_status"] == "review_required" for entry in blocked)
    assert all(
        "caller_evidence_and_terminal_disposition" in entry["guard_gap"]
        for entry in blocked
    )
    assert inventory["summary"]["overall_status"] == "blocked"


def test_task97_inventory_records_fail_closed_migrations_and_canonical_order_callers() -> None:
    inventory = _load_inventory()
    entries = {entry["path"]: entry for entry in inventory["entries"]}

    admin = entries["scripts/migrate_admin_capability_grants_schema.py"]
    assert admin["classification"] == "delete-executable"
    assert admin["gate"]["status"] == "BLOCKED"
    assert "fail-closed" in admin["gate"]["reason"]
    assert "not an absorbed compatibility success" in admin["gate"]["reason"]

    assert "scripts/migrate_order_contract_identity.py" not in entries
    assert "scripts/migrate_order_details_lifecycle_version_view.py" not in entries
    lifecycle = entries["scripts/migrate_order_lifecycle_control_facts.py"]
    assert lifecycle["classification"] == "delete-executable"
    assert "immutable-retirement-receipt" in lifecycle["guard_gap"]
    assert lifecycle["gate"]["status"] == "BLOCKED"

    for path in (
        "scripts/imports/adopt_historical_orders.py",
        "scripts/migrate_case_architecture_bootstrap_receipt_version_contract.py",
        "scripts/migrate_leave_substitution_holiday_only_batch_contract.py",
    ):
        entry = entries[path]
        assert entry["gate"]["status"] == "BLOCKED"
        assert "fail_closed" in " ".join(entry["guard_gap"])


def test_known_historical_import_operators_are_not_misreported_as_unknown_callers() -> None:
    inventory = _load_inventory()
    entries = {entry["path"]: entry for entry in inventory["entries"]}

    for path in (
        "scripts/imports/import_client_beclass.py",
        "scripts/imports/import_staff_beclass.py",
    ):
        entry = entries[path]
        assert entry["classification"] == "keep-operator-only"
        assert entry["capabilities"] == {
            "kind": "non-db-tool",
            "database": "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
        assert entry["gate"]["status"] == "PASS"
        assert entry["test"]["status"] == "passed"
        assert entry["receipt"]["status"] == "passed"
        assert "caller_evidence_and_terminal_disposition" not in entry["guard_gap"]

    for path in (
        "scripts/imports/adopt_historical_orders.py",
    ):
        entry = entries[path]
        assert entry["classification"] == "keep-operator-only"
        assert entry["capabilities"]["database"] == "read"
        assert entry["capabilities"]["production_mutation"] is False
        assert entry["capabilities"]["data_import"] is False
        assert entry["gate"]["status"] == "BLOCKED"
        assert "caller_evidence_and_terminal_disposition" not in entry["guard_gap"]

    finance_reprocess = entries["scripts/imports/reprocess_finance_import_batch.py"]
    assert finance_reprocess["classification"] == "keep-operator-only"
    assert finance_reprocess["capabilities"]["kind"] == "read-only-validator"
    assert finance_reprocess["capabilities"]["database"] == "read"
    assert finance_reprocess["required_guards"] == [
        "explicit_target_database",
        "configured_connected_host_match",
        "schema_fingerprint_or_plan_drift",
    ]
    assert finance_reprocess["guard_gap"] == ["none_required"]
    assert finance_reprocess["gate"]["status"] == "PASS"
    assert finance_reprocess["test"]["status"] == "passed"
    assert finance_reprocess["receipt"]["status"] == "passed"


def test_task97_inventory_records_governance_cli_drift_without_inventing_callers() -> None:
    inventory = _load_inventory()
    entries = {entry["path"]: entry for entry in inventory["entries"]}

    for path in (
        "scripts/generate_task97_entry_governance.py",
        "scripts/generate_task97_commit_dispositions.py",
        "scripts/generate_task97_production_script_inventory.py",
    ):
        entry = entries[path]
        assert entry["classification"] == "keep-operator-only"
        assert entry["capabilities"]["kind"] == "non-db-tool"
        assert entry["required_guards"] == []
        assert entry["guard_gap"] == ["none_required"]
        assert entry["gate"]["status"] == "PASS"
        assert entry["evidence"]["operator"] == "authorized architecture-governance operator"
        assert entry["callers"]["repository_search"]

    assert inventory["source"]["queue_cli_count"] == inventory["source"]["cli_count"]


def test_local_mysql_forward_has_exact_governed_launcher_caller() -> None:
    inventory = _load_inventory()
    entries = {entry["path"]: entry for entry in inventory["entries"]}
    forward = entries["scripts/launchers/local_mysql_tcp_forward.py"]

    assert forward["classification"] == "keep-operator-only"
    assert forward["capabilities"] == {
        "kind": "launcher",
        "database": "none",
        "production_mutation": False,
        "data_import": False,
        "process_launch": True,
    }
    assert forward["gate"]["status"] == "PASS"
    assert any(
        "manage_gcp_cloud_run_db_bridge.ps1" in caller
        for caller in forward["callers"]["repository_search"]
    )


def test_task97_guard_requirements_follow_source_capability() -> None:
    inventory = _load_inventory()
    entries = {entry["path"]: entry for entry in inventory["entries"]}

    exporter = entries["scripts/export_db_snapshot_fixture_v2.py"]
    assert exporter["capabilities"]["production_mutation"] is False
    assert exporter["capabilities"]["database"] == "read"
    assert exporter["classification"] == "test-only"
    assert exporter["required_guards"] == []
    assert "destructive_backup_receipt" not in exporter["guard_gap"]
    assert "explicit_apply_and_exact_confirmation" not in exporter["guard_gap"]

    validator = entries["scripts/validate_agent_governance.py"]
    assert validator["capabilities"]["kind"] == "read-only-validator"
    assert validator["classification"] == "keep-operator-only"
    assert validator["gate"]["status"] == "PASS"
    assert validator["test"]["status"] == "passed"
    assert validator["receipt"]["status"] == "passed"
    assert validator["capabilities"]["database"] == "none"
    assert validator["required_guards"] == []
    assert not {
        "explicit_target_database",
        "configured_connected_host_match",
        "schema_fingerprint_or_plan_drift",
        "destructive_backup_receipt",
    }.intersection(validator["guard_gap"])

    retirement = entries["scripts/validate_streamlit_retirement_readiness.py"]
    assert retirement["classification"] == "keep-operator-only"
    assert retirement["capabilities"]["kind"] == "read-only-validator"
    assert retirement["gate"]["status"] == "PASS"
    assert retirement["test"]["status"] == "passed"
    assert retirement["receipt"]["status"] == "passed"

    for path in (
        "scripts/verify_validation_schema_manifest.py",
        "scripts/verify_verification_receipts.py",
    ):
        read_only_verifier = entries[path]
        assert read_only_verifier["classification"] == "keep-operator-only"
        assert read_only_verifier["capabilities"] == {
            "kind": "read-only-validator",
            "database": "none",
            "production_mutation": False,
            "data_import": False,
            "process_launch": False,
        }
        assert read_only_verifier["required_guards"] == []
        assert read_only_verifier["guard_gap"] == ["none_required"]
        assert read_only_verifier["gate"]["status"] == "PASS"
        assert read_only_verifier["test"]["status"] == "passed"
        assert read_only_verifier["receipt"]["status"] == "passed"

    mutator = entries["scripts/import_db_snapshot_fixture_v2.py"]
    assert mutator["classification"] == "test-only"
    assert mutator["capabilities"]["production_mutation"] is False
    assert mutator["required_guards"] == []
    assert mutator["gate"]["status"] == "PASS"

    fixture_dates = entries["scripts/reconcile_fixture_order_dates_v2.py"]
    assert fixture_dates["classification"] == "test-only"
    assert fixture_dates["capabilities"]["production_mutation"] is False
    assert fixture_dates["required_guards"] == []
    assert fixture_dates["gate"] == {
        "status": "PASS",
        "reason": "test-only entry is bounded to its allowlisted disposable target",
    }
    assert fixture_dates["test"]["status"] == "passed"
    assert fixture_dates["receipt"]["status"] == "passed"
    assert fixture_dates["replacement"] == (
        "none; disposable lu_test_* read-only fixture audit"
    )

    blocked_paths = {
        entry["path"]
        for entry in inventory["entries"]
        if entry["gate"]["status"] == "BLOCKED"
    }
    assert len(blocked_paths) == 15
    assert "scripts/verify_validation_schema_manifest.py" not in blocked_paths
    assert "scripts/verify_verification_receipts.py" not in blocked_paths
    assert "scripts/imports/reprocess_finance_import_batch.py" not in blocked_paths
    assert "scripts/migrate_client_identity_status_source.py" not in {
        entry["path"] for entry in inventory["entries"]
    }
    assert "scripts/rebuild_beclass_import_anomalies.py" not in {
        entry["path"] for entry in inventory["entries"]
    }


def test_task97_inventory_has_no_null_or_empty_evidence_fields() -> None:
    inventory = _load_inventory()

    def assert_populated(value, location: str) -> None:
        assert value is not None, location
        assert value != "", location
        if location.endswith(".required_guards"):
            return
        assert value != [], location
        if isinstance(value, dict):
            for key, child in value.items():
                assert_populated(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                assert_populated(child, f"{location}[{index}]")

    for index, entry in enumerate(inventory["entries"]):
        assert_populated(entry, f"entries[{index}]")
