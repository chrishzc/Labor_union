import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_22_order_terms_optional_downstream_versions_v1.json"
ARTIFACT = "1044_order_terms_optional_downstream_versions.sql"


def _snapshot(*, nullable: str) -> dict[str, object]:
    return {
        "columns": [
            {
                "table_name": "order_terms_apply_receipts",
                "column_name": column,
                "column_type": "bigint unsigned",
                "is_nullable": nullable,
                "column_default": None,
                "extra": "",
            }
            for column in ("client_finance_version", "payroll_version")
        ],
        "indexes": [],
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_release_is_schema_only_and_hash_locked():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    artifact_path = ROOT / artifact["relative_path"]
    descriptor_path = ROOT / manifest["descriptor_artifact"]["relative_path"]

    assert manifest["source_baseline"]["baseline_id"] == (
        "labor-union-order-details-owner-dates-2026-09-15-v1"
    )
    assert artifact["data_effect"] == "schema_only"
    assert manifest["backfills"] == []
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256(descriptor_path.read_bytes()).hexdigest() == (
        manifest["descriptor_artifact"]["sha256"]
    )


def test_fresh_schema_and_preserve_bridge_share_nullable_contract():
    fresh = (ROOT / "db/schema_parts/227_order_terms_optional_downstream_versions.sql").read_text(
        encoding="utf-8"
    )
    bridge = (ROOT / "db/schema_parts/1044_order_terms_optional_downstream_versions.sql").read_text(
        encoding="utf-8"
    )

    for source in (fresh, bridge):
        assert "client_finance_version BIGINT UNSIGNED NULL" in source
        assert "payroll_version BIGINT UNSIGNED NULL" in source


def test_release_descriptor_classifies_predecessor_successor_and_drift():
    manifest = load_migration_release_manifest(MANIFEST, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)

    for kind in ("tables", "parent_columns", "indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])
    assert migration.local_additive_descriptor_state(
        _snapshot(nullable="NO"), canonical, ARTIFACT
    ) == "absent"
    assert migration._release_descriptor_metadata_state(
        _snapshot(nullable="NO"), ARTIFACT, released
    ) == "absent"
    assert migration.local_additive_descriptor_state(
        _snapshot(nullable="YES"), canonical, ARTIFACT
    ) == "exact"

    drift = _snapshot(nullable="YES")
    drift["columns"][0]["column_type"] = "bigint"
    assert migration.local_additive_descriptor_state(
        drift, canonical, ARTIFACT
    ) == "drift"
