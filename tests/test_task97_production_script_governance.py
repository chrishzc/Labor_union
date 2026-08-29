"""Focused integrity checks for the Task 97 production-script evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


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
    "keep-operator-only": 38,
    "test-only": 10,
    "rewrite-to-canonical-runner": 28,
    "delete-executable": 2,
    "blocked-caller-evidence": 10,
}


def _load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_task97_script_inventory_is_complete_and_current() -> None:
    inventory = _load_inventory()
    entries = inventory["entries"]

    assert inventory["contract"] == "task97-production-script-inventory/v1"
    assert inventory["source"]["cli_count"] == 88
    assert len(entries) == 88
    assert inventory["summary"]["total"] == 88

    identities = [entry["exact_id"] for entry in entries]
    paths = [entry["path"] for entry in entries]
    assert len(set(identities)) == 88
    assert len(set(paths)) == 88
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
        if entry["classification"] == "test-only":
            assert entry["gate"]["status"] == "PASS"
        else:
            assert entry["gate"]["status"] == "BLOCKED"


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
    }

    blocked = [
        entry
        for entry in inventory["entries"]
        if entry["classification"] == "blocked-caller-evidence"
    ]
    assert len(blocked) == 10
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
    assert admin["classification"] == "blocked-caller-evidence"
    assert admin["gate"]["status"] == "BLOCKED"
    assert "fail-closed" in admin["gate"]["reason"]
    assert "not an absorbed compatibility success" in admin["gate"]["reason"]

    for path in (
        "scripts/migrate_order_contract_identity.py",
        "scripts/migrate_order_details_lifecycle_version_view.py",
        "scripts/migrate_order_lifecycle_control_facts.py",
    ):
        entry = entries[path]
        assert entry["callers"]["runtime_registration"] == [
            "scripts/migrate_preserved_database_additive_schema.py::run_candidate_post_schema -> _run_project_python("
            + path
            + ")"
        ]
        assert "canonical_runner_absorption_not_complete" in entry["guard_gap"]
        assert entry["gate"]["status"] == "BLOCKED"

    for path in (
        "scripts/imports/adopt_historical_orders.py",
        "scripts/imports/import_client_beclass.py",
        "scripts/imports/import_staff_beclass.py",
        "scripts/migrate_case_architecture_bootstrap_receipt_version_contract.py",
        "scripts/migrate_leave_substitution_holiday_only_batch_contract.py",
    ):
        entry = entries[path]
        assert entry["gate"]["status"] == "BLOCKED"
        assert "fail_closed" in " ".join(entry["guard_gap"])


def test_task97_inventory_has_no_null_or_empty_evidence_fields() -> None:
    inventory = _load_inventory()

    def assert_populated(value, location: str) -> None:
        assert value is not None, location
        assert value != "", location
        assert value != [], location
        if isinstance(value, dict):
            for key, child in value.items():
                assert_populated(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                assert_populated(child, f"{location}[{index}]")

    for index, entry in enumerate(inventory["entries"]):
        assert_populated(entry, f"entries[{index}]")
