"""Pure metadata/text checks: no SQL, cursor, DB or provider execution."""
from copy import deepcopy
from pathlib import Path
import runpy

import pytest
from scripts import migrate_preserved_database_additive_schema as migration
from scripts.build_validation_schema_release import verify_release
from scripts.compact_fresh_schema import load_compact_plan
from scripts.verify_validation_schema_manifest import load_manifest
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
ARTIFACT = "1073_contract_document_render_snapshot.sql"
ORIGINAL = "166_contract_signing_workflow.sql"
TABLE = "contract_document_versions"
CHECK = (TABLE, "chk_contract_document_render_source")
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_11_06_controlled_purpose_media_reference_v1.json"
NEW_COLUMNS = {
    "render_source_kind", "render_source_snapshot", "render_source_snapshot_sha256",
    "render_source_sha256", "render_source_size_bytes",
}
# Reuse the adjacent pure metadata fixture; the module only defines tests/functions.
_snapshot = runpy.run_path(str(Path(__file__).with_name(
    "test_controlled_purpose_media_reference_schema.py"
)))["_snapshot"]


def test_release_binds_closed_source_and_preserves_original_contracts():
    release = load_migration_release_manifest(MANIFEST, ROOT)
    released = release.owned_object_descriptors(ROOT)[ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    assert {k: v for k, v in released.items() if k != "triggers"} == {
        k: v for k, v in canonical.items() if k != "triggers"
    }
    assert released["triggers"] == set(canonical["triggers"])
    assert release.backfills == ()
    fields = canonical["parent_columns"][TABLE]
    assert fields["render_source_kind"] == {
        "column_type": "enum('legacy_archived','render_snapshot')",
        "is_nullable": "NO", "column_default": "legacy_archived", "extra": "",
    }
    assert fields["render_source_snapshot"]["column_type"] == "json"
    assert fields["render_source_size_bytes"]["column_type"] == "bigint unsigned"
    assert fields["media_asset_id"] == {
        "column_type": "bigint", "is_nullable": "YES", "column_default": None, "extra": "",
    }
    original = migration._canonical_artifact_descriptor(ORIGINAL)
    assert set(fields) == set(original["tables"][TABLE]) | NEW_COLUMNS
    assert len(fields) == 22
    assert canonical["foreign_keys"] == {key: value for key, value in original["foreign_keys"].items() if key[0] == TABLE}
    assert len(canonical["foreign_keys"]) == 6
    assert len(canonical["checks"]) == 4
    assert len(canonical["triggers"]) == 2
    for key, clause in original["checks"].items():
        if key[0] == TABLE:
            assert canonical["checks"][key] == clause


def test_metadata_accepts_only_exact_legacy_or_complete_snapshot_parent():
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    state = lambda value: migration.local_additive_descriptor_state(value, descriptor, ARTIFACT)
    current = _snapshot(descriptor)
    assert state(current) == "exact"
    predecessor = deepcopy(descriptor)
    for name in NEW_COLUMNS:
        predecessor["parent_columns"][TABLE].pop(name)
    predecessor["parent_columns"][TABLE]["media_asset_id"]["is_nullable"] = "NO"
    predecessor["checks"].pop(CHECK)
    assert state(_snapshot(predecessor)) == "absent"
    for name, field, value in (
        ("media_asset_id", "column_type", "bigint unsigned"),
        ("media_asset_id", "is_nullable", "NO"),
        ("render_source_kind", "column_default", "render_snapshot"),
        ("render_source_snapshot", "column_type", "longtext"),
        ("render_source_size_bytes", "column_type", "bigint"),
    ):
        damaged = deepcopy(current)
        next(row for row in damaged["columns"] if row["column_name"] == name)[field] = value
        assert state(damaged) == "drift"
    for missing in (CHECK[1], "fk_contract_document_media_asset"):
        damaged = deepcopy(current)
        damaged["constraints"] = [row for row in damaged["constraints"] if row["constraint_name"] != missing]
        assert state(damaged) == "partial"
    damaged = deepcopy(current)
    damaged["triggers"] = damaged["triggers"][1:]
    assert state(damaged) == "partial"
    damaged = deepcopy(current)
    damaged["columns"] = [row for row in damaged["columns"] if row["column_name"] != "render_source_snapshot"]
    assert state(damaged) == "drift"
    damaged = deepcopy(current)
    next(row for row in damaged["constraints"] if row["constraint_name"] == CHECK[1])["check_clause"] = "media_asset_id IS NULL"
    assert state(damaged) == "drift"


def test_166_projection_accepts_selected_successor_and_retains_guards():
    original = migration._canonical_artifact_descriptor(ORIGINAL)
    assert migration._canonical_artifact_metadata_state(_snapshot(original), ORIGINAL) == "exact"
    successor = migration._canonical_artifact_descriptor(ARTIFACT)
    current = deepcopy(original)
    current["tables"][TABLE] = successor["parent_columns"][TABLE]
    current["checks"].update(successor["checks"])
    now = _snapshot(current)
    assert migration._canonical_artifact_metadata_state(now, ORIGINAL) == "exact"
    assert migration.local_additive_descriptor_state(now, original, ORIGINAL) == "exact"
    next(row for row in now["triggers"] if row["trigger_name"] == "trg_contract_document_versions_before_update")["action_statement"] = "BEGIN SET @unsafe=1; END"
    assert migration._canonical_artifact_metadata_state(now, ORIGINAL) == "drift"


def test_single_exact_alter_and_current_text_bind_same_snapshot_contract():
    statement, = migration.split_sql((ROOT / "db/schema_parts" / ARTIFACT).read_text())
    assert migration._local_classify_statement(statement) == "contract_render_snapshot_source_successor"
    with pytest.raises(migration.LocalAdditiveBlocked, match="noncanonical"):
        migration._local_classify_statement(statement.replace("BIGINT NULL", "BIGINT NOT NULL"))
    assert "DROP " not in statement.upper()
    for value in ("contract-render-source.v1", "canonical-xlsx-zip.v1", "$.source.matching_plan_id", "$.source.matching_segment_id", "$.source.facts_snapshot_sha256"):
        assert value in statement
    assert "JSON_LENGTH(render_source_snapshot) = 4" in statement
    assert "JSON_LENGTH(JSON_EXTRACT(render_source_snapshot, '$.source')) = 9" in statement
    assert "render_source_size_bytes IS NULL" in statement
    assert "render_source_size_bytes IS NOT NULL AND render_source_size_bytes > 0" in statement
    assert verify_release(load_manifest()) == []
    assert load_manifest()["schema_parts"]["terminal_artifact"] == ARTIFACT
    create, = (step["sql"] for step in load_compact_plan()["steps"] if step["sql"].startswith(f"CREATE TABLE `{TABLE}`"))
    canonical = migration._canonical_artifact_descriptor(ARTIFACT)
    checks = migration._show_create_check_clauses(create)
    assert migration._normalize_check_contract(checks[CHECK]) == migration._normalize_check_contract(canonical["checks"][CHECK])
    assert "`media_asset_id` bigint DEFAULT NULL" in create
    assert "DEFAULT 'legacy_archived'" in create
