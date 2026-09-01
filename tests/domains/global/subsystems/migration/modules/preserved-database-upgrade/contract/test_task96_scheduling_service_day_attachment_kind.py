"""Contract coverage for the 1025 -> 1026 preserve-data successor chain."""

from __future__ import annotations

from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1026_task96_scheduling_service_day_attachment_kind.sql"
MANIFEST_NAME = (
    "labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.json"
)
PREDECESSOR_RELEASE = (
    "labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.json"
)


def _snapshot(column_type: str) -> dict[str, list[dict[str, object]] | dict[str, object]]:
    return {
        "columns": [{
            "table_name": "scheduling_service_day_log_attachments",
            "column_name": "attachment_kind",
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


def test_task96_attachment_kind_release_is_after_1025_and_hash_bound() -> None:
    configured = migration.DEFAULT_RELEASE_MANIFESTS
    predecessor_position = configured.index(PREDECESSOR_RELEASE)
    assert configured[predecessor_position + 1] == MANIFEST_NAME

    manifest = load_migration_release_manifest(ROOT / "db/migration_releases" / MANIFEST_NAME, ROOT)
    assert manifest.schema_paths(ROOT) == (
        (ROOT / "db/schema_parts" / ARTIFACT).resolve(),
    )
    assert manifest.backfills == ()

    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert released["tables"] == {}
    assert released["parent_columns"] == canonical["parent_columns"]
    assert released["indexes"] == {}
    assert released["foreign_keys"] == {}
    assert released["checks"] == {}
    assert released["triggers"] == set()


def test_task96_attachment_kind_accepts_only_exact_meal_photo_predecessor() -> None:
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    predecessor = _snapshot("enum('meal_photo')")
    assert migration.local_additive_descriptor_state(
        predecessor, descriptor, ARTIFACT
    ) == "absent"
    manifest = load_migration_release_manifest(ROOT / "db/migration_releases" / MANIFEST_NAME, ROOT)
    released = manifest.owned_object_descriptors(ROOT)[ARTIFACT]
    assert migration._release_descriptor_metadata_state(
        predecessor, ARTIFACT, released
    ) == "absent"

    successor = _snapshot("enum('meal_photo','baby_log_photo')")
    assert migration.local_additive_descriptor_state(
        successor, descriptor, ARTIFACT
    ) == "exact"

    drift = _snapshot("enum('meal_photo','other_photo')")
    assert migration.local_additive_descriptor_state(
        drift, descriptor, ARTIFACT
    ) == "drift"
