"""Contract coverage for the Issue #276 registry owner schema release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
FRESH_ARTIFACT = "219_registry_owner_mutations.sql"
PRESERVE_ARTIFACT = "1036_registry_owner_mutations.sql"
MANIFEST = "labor_union_2026_09_11_registry_owner_mutations_v1.json"
DESCRIPTORS = "labor_union_2026_09_11_registry_owner_mutations_v1.descriptors.json"
TABLES = {
    "client_profile_admin_change_events",
    "beclass_record_correction_states",
    "beclass_record_correction_events",
    "staff_profile_change_events",
    "staff_bank_account_states",
    "staff_bank_account_events",
}
TRIGGERS = {
    "trg_client_profile_admin_change_events_before_update",
    "trg_client_profile_admin_change_events_before_delete",
    "trg_beclass_record_correction_events_before_update",
    "trg_beclass_record_correction_events_before_delete",
    "trg_staff_profile_change_events_before_update",
    "trg_staff_profile_change_events_before_delete",
    "trg_staff_bank_account_events_before_update",
    "trg_staff_bank_account_events_before_delete",
}


def test_release_is_hash_bound_latest_and_linked_to_fresh_assembly() -> None:
    manifest_path = ROOT / "db/migration_releases" / MANIFEST
    descriptor_path = manifest_path.with_name(DESCRIPTORS)
    sql_path = ROOT / "db/schema_parts" / PRESERVE_ARTIFACT
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assembly = json.loads((
        ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json"
    ).read_text(encoding="utf-8"))

    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST
    assert raw["source_baseline"]["baseline_id"] == (
        "labor-union-weekly-report-metrics-2026-09-09-v1"
    )
    assert raw["artifacts"][0]["sha256"] == hashlib.sha256(
        sql_path.read_bytes()
    ).hexdigest()
    assert raw["descriptor_artifact"]["sha256"] == hashlib.sha256(
        descriptor_path.read_bytes()
    ).hexdigest()
    assert f"db/schema_parts/{FRESH_ARTIFACT}" in assembly["active_bootstrap"]
    assert assembly["classifications"][f"db/schema_parts/{PRESERVE_ARTIFACT}"] == (
        "migration-only"
    )


def test_descriptor_covers_parent_columns_tables_metadata_and_triggers() -> None:
    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / MANIFEST,
        ROOT,
    )
    released = manifest.owned_object_descriptors(ROOT)[PRESERVE_ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(PRESERVE_ARTIFACT)

    assert set(released["tables"]) == TABLES
    assert released["tables"] == {
        table: set(columns) for table, columns in canonical["tables"].items()
    }
    assert set(released["parent_columns"]) == {"staff", "staff_bank_accounts"}
    assert released["parent_columns"]["staff"]["staff_profile_version"] == {
        "column_type": "bigint unsigned",
        "is_nullable": "NO",
        "column_default": "0",
        "extra": "",
    }
    assert released["parent_columns"]["staff_bank_accounts"]["is_active"] == {
        "column_type": "tinyint(1)",
        "is_nullable": "NO",
        "column_default": "1",
        "extra": "",
    }
    for kind in ("indexes", "foreign_keys", "checks", "parent_columns"):
        assert released[kind] == canonical[kind]
    assert released["triggers"] == set(canonical["triggers"]) == TRIGGERS


def test_preserve_artifact_matches_fresh_schema_without_data_rewrite() -> None:
    fresh = (ROOT / "db/schema_parts" / FRESH_ARTIFACT).read_text(encoding="utf-8")
    preserve = (ROOT / "db/schema_parts" / PRESERVE_ARTIFACT).read_text(
        encoding="utf-8"
    )

    shared_suffix = "CREATE TABLE IF NOT EXISTS client_profile_admin_change_events"
    assert fresh[fresh.index(shared_suffix):] == preserve[preserve.index(shared_suffix):]
    assert "ALTER TABLE `staff`\n    ADD COLUMN `staff_profile_version`" in preserve
    assert "ALTER TABLE `staff_bank_accounts`\n    ADD UNIQUE KEY" in preserve
    assert "ALTER TABLE `staff_bank_accounts`\n    ADD COLUMN `is_active`" in preserve
    assert all(
        migration._local_classify_statement(statement)
        for statement in migration.split_sql(preserve)
    )
    assert "INSERT INTO" not in preserve
    assert re.search(r"(?im)^\s*(?:INSERT|UPDATE|DELETE)\b", preserve) is None
    assert re.search(r"(?im)^\s*DROP\s+TABLE\b", preserve) is None
