import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_09_14_order_service_hours_half_precision_v1.json"
ARTIFACT = "1040_order_service_hours_half_precision.sql"


def _snapshot(column_type: str, *, with_check: bool) -> dict[str, object]:
    constraints = []
    if with_check:
        constraints.append({
            "table_name": "orders",
            "constraint_name": "chk_orders_service_hours_half_hour",
            "constraint_type": "CHECK",
            "check_clause": (
                "service_hours_per_day >= 0 AND service_hours_per_day <= 24 "
                "AND ((service_hours_per_day * 2) % 1) = 0"
            ),
            "enforced": "YES",
        })
    return {
        "columns": [{
            "table_name": "orders",
            "column_name": "service_hours_per_day",
            "column_type": column_type,
            "is_nullable": "YES",
            "column_default": "0" if column_type == "int" else "0.0",
            "extra": "",
        }],
        "indexes": [],
        "constraints": constraints,
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_half_hour_release_preserves_rows_and_owns_decimal_column_contract():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][0]
    artifact_path = ROOT / artifact["relative_path"]
    descriptor_path = ROOT / manifest["descriptor_artifact"]["relative_path"]
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))

    assert manifest["source_baseline"]["baseline_id"] == "labor-union-matching-plan-create-receipts-2026-09-12-v1"
    assert artifact["data_effect"] == "schema_only"
    assert manifest["backfills"] == []
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    assert hashlib.sha256(descriptor_path.read_bytes()).hexdigest() == manifest["descriptor_artifact"]["sha256"]
    owned = descriptor["descriptors"][artifact["name"]]
    assert owned["parent_columns"]["orders"]["service_hours_per_day"]["column_type"] == "decimal(4,1)"
    assert "orders.chk_orders_service_hours_half_hour" in owned["checks"]


def test_fresh_schema_and_preserve_bridge_share_half_hour_contract():
    fresh = (ROOT / "db/schema_parts/223_order_service_hours_half_precision.sql").read_text(encoding="utf-8")
    bridge = (ROOT / "db/schema_parts/1040_order_service_hours_half_precision.sql").read_text(encoding="utf-8")

    for source in (fresh, bridge):
        assert "service_hours_per_day DECIMAL(4, 1)" in source
        assert "chk_orders_service_hours_half_hour" in source
        assert "MOD(service_hours_per_day * 2, 1) = 0" in source


def test_half_hour_release_descriptor_matches_canonical_and_classifies_states():
    manifest = load_migration_release_manifest(MANIFEST, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)

    for kind in ("tables", "parent_columns", "indexes", "foreign_keys", "checks"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"])
    predecessor = _snapshot("int", with_check=False)
    assert migration.local_additive_descriptor_state(
        predecessor, canonical, ARTIFACT
    ) == "absent"
    assert migration._release_descriptor_metadata_state(
        predecessor, ARTIFACT, released
    ) == "absent"
    assert migration.local_additive_descriptor_state(
        _snapshot("decimal(4,1)", with_check=True), canonical, ARTIFACT
    ) == "exact"
    assert migration.local_additive_descriptor_state(
        _snapshot("decimal(4,2)", with_check=True), canonical, ARTIFACT
    ) == "drift"
