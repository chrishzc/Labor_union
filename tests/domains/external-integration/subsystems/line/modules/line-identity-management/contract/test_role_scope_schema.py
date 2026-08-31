"""Static contract for the additive LINE identity role-scope successor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
SQL_PATH = ROOT / "db/schema_parts/1019_line_identity_role_scope.sql"
MANIFEST_PATH = (
    ROOT
    / "db/migration_releases/labor_union_2026_08_30_line_identity_role_scope_v1.json"
)
DESCRIPTOR_PATH = (
    ROOT
    / "db/migration_releases/labor_union_2026_08_30_line_identity_role_scope_v1.descriptors.json"
)


def test_role_scope_release_is_hash_bound_and_ordered_in_fresh_assembly() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptor = json.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assembly = json.loads(
        (ROOT / "db/schema_assembly/labor_union_fresh_schema_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(
        SQL_PATH.read_bytes()
    ).hexdigest()
    assert manifest["descriptor_artifact"]["sha256"] == hashlib.sha256(
        DESCRIPTOR_PATH.read_bytes()
    ).hexdigest()
    assert descriptor["release_id"] == manifest["release_id"]
    role_scope = "db/schema_parts/1019_line_identity_role_scope.sql"
    current_terminal = "db/schema_parts/1020_historical_owner_payment_settlement.sql"
    assert role_scope in assembly["active_bootstrap"]
    assert assembly["active_bootstrap"].index(role_scope) < assembly[
        "active_bootstrap"
    ].index(current_terminal)


def test_schema_has_one_shared_role_root_event_stream_active_role_and_streak() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS line_identity_role_bindings" in sql
    assert "PRIMARY KEY (line_user_id, subject_type)" in sql
    assert "CREATE TABLE IF NOT EXISTS line_identity_role_binding_events" in sql
    assert "REFERENCES line_identity_role_bindings(line_user_id, subject_type)" in sql
    assert (
        "ADD COLUMN selected_identity_role ENUM(''customer'',''staff'') NULL"
        in sql
    )
    assert "@line_selected_role_column_any = 0" in sql
    assert "@line_selected_role_column_exact = 1" in sql
    assert "FAIL_CLOSED_LINE_SELECTED_ROLE_INVALID_SPEC" in sql
    assert sql.count("ALTER TABLE line_platform_users ADD COLUMN selected_identity_role") == 1
    assert "CREATE TABLE IF NOT EXISTS line_identity_binding_failure_streaks" in sql
    assert "line_user_id VARCHAR(191) PRIMARY KEY" in sql
    assert "candidate_scope VARCHAR(191) NOT NULL" in sql
    assert "escalation_id BIGINT NULL" in sql
    assert "escalation_id BIGINT UNSIGNED" not in sql
    assert "CHECK (failure_count BETWEEN 0 AND 2)" in sql

    assert "FROM clients" not in sql
    assert "FROM staff" not in sql
    assert "FROM admin_users" not in sql
    assert "DROP TABLE" not in sql
    assert "TRUNCATE" not in sql


def test_preserve_data_backfill_only_consumes_legacy_canonical_roots_and_events() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "FROM line_identity_bindings AS legacy" in sql
    assert "FROM line_identity_binding_events AS legacy_event" in sql
    assert "legacy.binding_status <> 'unbound'" in sql
    assert "legacy_event.subject_type IS NOT NULL" in sql


def test_released_descriptor_matches_canonical_owned_object_contract() -> None:
    released = load_migration_release_manifest(
        MANIFEST_PATH,
        ROOT,
    ).owned_object_descriptors(ROOT)[SQL_PATH.name]
    canonical = migration._canonical_artifact_descriptor(SQL_PATH.name)

    assert released["tables"] == {
        table: set(columns) for table, columns in canonical["tables"].items()
    }
    for contract_kind in ("indexes", "foreign_keys", "checks"):
        assert released[contract_kind] == canonical[contract_kind]
    assert released["triggers"] == set(canonical["triggers"])
    assert set(canonical["parent_columns"]) == {"line_platform_users"}
    assert set(canonical["parent_columns"]["line_platform_users"]) == {
        "selected_identity_role"
    }
