"""Contract coverage for the historical-order pairing resolution enum successor."""

from __future__ import annotations

from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1027_historical_order_pairing_resolution_reused.sql"
MANIFEST_NAME = (
    "labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json"
)
PREDECESSOR_ENUM = (
    "enum('blank','staff_missing','staff_ambiguous','evidence_only',"
    "'assignment_candidate','assignment_conflict')"
)
SUCCESSOR_ENUM = (
    "enum('blank','staff_missing','staff_ambiguous','evidence_only',"
    "'assignment_candidate','assignment_reused','assignment_conflict')"
)


def _snapshot(column_type: str) -> dict[str, object]:
    return {
        "columns": [{
            "table_name": "historical_order_pairing_evidence",
            "column_name": "resolution",
            "column_type": column_type,
            "is_nullable": "NO",
            "column_default": None,
            "extra": "",
        }],
        "indexes": [],
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_pairing_resolution_release_is_ordered_and_hash_bound() -> None:
    configured = migration.DEFAULT_RELEASE_MANIFESTS
    assert MANIFEST_NAME in configured
    assert configured.index(MANIFEST_NAME) < configured.index(
        "labor_union_2026_09_01_historical_service_accounting_v1.json"
    )

    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / MANIFEST_NAME,
        ROOT,
    )
    assert manifest.schema_paths(ROOT) == (
        (ROOT / "db/schema_parts" / ARTIFACT).resolve(),
    )
    assert manifest.backfills == ()

    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["parent_columns"] == canonical["parent_columns"]


def test_pairing_resolution_accepts_only_exact_released_predecessor() -> None:
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    predecessor = _snapshot(PREDECESSOR_ENUM)
    assert migration.local_additive_descriptor_state(
        predecessor, descriptor, ARTIFACT
    ) == "absent"

    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / MANIFEST_NAME,
        ROOT,
    )
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    assert migration._release_descriptor_metadata_state(
        predecessor, ARTIFACT, released
    ) == "absent"

    assert migration.local_additive_descriptor_state(
        _snapshot(SUCCESSOR_ENUM), descriptor, ARTIFACT
    ) == "exact"
    assert migration.local_additive_descriptor_state(
        _snapshot(PREDECESSOR_ENUM.replace("assignment_conflict", "other")),
        descriptor,
        ARTIFACT,
    ) == "drift"
