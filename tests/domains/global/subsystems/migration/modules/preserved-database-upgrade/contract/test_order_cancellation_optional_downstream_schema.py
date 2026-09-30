"""Cancellation receipt schema upgrades preserve values and reject metadata drift."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import validate_schema_assembly
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_29_order_cancellation_optional_downstream_v1.json"
ARTIFACT = "1048_order_cancellation_optional_downstream.sql"
FIELDS = {"scheduling_command_receipt_id": "bigint", "scheduling_version": "bigint unsigned", "scheduling_generation": "int unsigned", "client_finance_version": "bigint unsigned", "payroll_version": "bigint unsigned"}


def _snapshot(nullable):
    return {"columns": [{"table_name": "order_cancellation_apply_receipts", "column_name": name, "column_type": kind, "is_nullable": nullable, "column_default": None, "extra": ""} for name, kind in FIELDS.items()], "indexes": [], "constraints": [], "key_columns": [], "foreign_keys": [], "triggers": [], "show_create_tables": {}, "views": []}


def test_release_is_hash_locked_schema_only_and_assembled():
    release = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert release["backfills"] == []
    assert release["artifacts"][0]["data_effect"] == "schema_only"
    for item in (release["artifacts"][0], release["descriptor_artifact"]):
        assert hashlib.sha256((ROOT / item["relative_path"]).read_bytes()).hexdigest() == item["sha256"]
    assert validate_schema_assembly() == []
    fresh = (ROOT / "db/schema_parts/229_order_cancellation_optional_downstream.sql").read_text(encoding="utf-8")
    bridge = (ROOT / "db/schema_parts" / ARTIFACT).read_text(encoding="utf-8")
    assert fresh == bridge
    assert "UPDATE " not in bridge and "DELETE " not in bridge and "DROP " not in bridge
    statements = migration.split_sql(bridge)
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == "order_cancellation_downstream_nullability_widen"
    import pytest
    with pytest.raises(migration.LocalAdditiveBlocked):
        migration._local_classify_statement(statements[0].replace("client_finance_version BIGINT UNSIGNED NULL", "client_finance_version INT NULL"))


def test_release_classifies_predecessor_successor_partial_and_drift():
    released = load_migration_release_manifest(MANIFEST, ROOT).owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    for kind in ("tables", "parent_columns", "indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert migration.local_additive_descriptor_state(_snapshot("NO"), canonical, ARTIFACT) == "absent"
    assert migration.local_additive_descriptor_state(_snapshot("YES"), canonical, ARTIFACT) == "exact"
    partial = _snapshot("NO")
    partial["columns"][0]["is_nullable"] = "YES"
    assert migration.local_additive_descriptor_state(partial, canonical, ARTIFACT) == "drift"
    drift = deepcopy(_snapshot("YES"))
    drift["columns"][1]["column_type"] = "bigint"
    assert migration.local_additive_descriptor_state(drift, canonical, ARTIFACT) == "drift"
