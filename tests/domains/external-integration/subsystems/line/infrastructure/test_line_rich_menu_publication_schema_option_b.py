"""
File: test_line_rich_menu_publication_schema_option_b.py
Description: 驗證 Rich Menu Option B additive schema、release descriptor 與 immutable 契約。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.migrate_preserved_database_additive_schema as migration
import shared_kernel.migration_release as release_contract
from scripts.schema_assembly import load_schema_assembly
from scripts.verify_validation_schema_manifest import verify_manifest
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)
PART_NAME = "1001_line_rich_menu_publication_step_saga.sql"
MANIFEST_PATH = (
    ROOT
    / "db/migration_releases/"
    / "labor_union_2026_08_20_line_rich_menu_publication_step_saga_v1.json"
)
DESCRIPTOR_PATH = (
    ROOT
    / "db/migration_releases/"
    / "labor_union_2026_08_20_line_rich_menu_publication_step_saga_v1.descriptors.json"
)


def test_option_b_part_is_additive_and_immutable() -> None:
    sql = (ROOT / "db/schema_parts" / PART_NAME).read_text(encoding="utf-8")
    assert "line_rich_menu_publication_step_receipts" not in sql
    for table in (
        "line_rich_menu_publication_step_acknowledgements",
        "line_rich_menu_publication_step_attempt_events",
        "line_rich_menu_publication_cleanup_anomalies",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
        assert f"BEFORE UPDATE ON {table}" in sql
        assert f"BEFORE DELETE ON {table}" in sql
    assert "INSERT " not in sql.upper()
    assert "ALTER TABLE" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()


def test_option_b_manifest_descriptor_and_assembly_are_hash_locked() -> None:
    manifest = load_migration_release_manifest(MANIFEST_PATH, ROOT)
    assert manifest.schema_paths(ROOT)[0].name == PART_NAME
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    owned = descriptor["descriptors"][PART_NAME]
    assert set(owned["tables"]) == {
        "line_rich_menu_publication_step_acknowledgements",
        "line_rich_menu_publication_step_attempt_events",
        "line_rich_menu_publication_cleanup_anomalies",
    }
    assert len(owned["triggers"]) == 6
    assert len(owned["indexes"]) == 11
    assert len(owned["foreign_keys"]) == 3
    assert len(owned["checks"]) == 7
    normalized = manifest.owned_object_descriptors(ROOT)[PART_NAME]
    canonical = migration._canonical_artifact_descriptor(PART_NAME)
    for kind in ("indexes", "foreign_keys", "checks"):
        assert normalized[kind] == canonical[kind]
    assembly = load_schema_assembly()
    assert PART_NAME in {path.name for path in assembly.active_artifact_paths}
    assert verify_manifest(
        json.loads(
            (ROOT / "db/cutover_releases/labor_union_validation_schema_v1.json")
            .read_text(encoding="utf-8")
        )
    ) == []


def test_option_b_release_declares_no_backfill_or_seed() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["backfills"] == []
    assert payload["artifacts"][0]["data_effect"] == "schema_only"
    assert "line-rich-menu-publication-step-saga-v1" in payload[
        "application_compatibility"
    ]["compatible_contracts"]


def test_option_b_full_descriptor_drift_fails_closed() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH, ROOT
    ).owned_object_descriptors(ROOT)[PART_NAME]
    released["indexes"] = dict(released["indexes"])
    released["indexes"].pop(next(iter(released["indexes"])))
    with pytest.raises(migration.UpgradeBlocked, match="differs from canonical SQL"):
        migration._release_descriptor_metadata_state({}, PART_NAME, released)


def test_legacy_descriptor_remains_valid_but_partial_metadata_fails_closed() -> None:
    legacy = {"legacy.sql": {"tables": {"legacy": ["id"]}, "triggers": []}}
    release_contract._validate_descriptor_shapes(legacy)
    legacy["legacy.sql"]["indexes"] = {}
    with pytest.raises(ValueError, match="must be declared together"):
        release_contract._validate_descriptor_shapes(legacy)
