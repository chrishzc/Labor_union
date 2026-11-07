"""Pure release/metadata checks: no SQL driver, cursor, DB or provider calls."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.build_validation_schema_release import verify_release
from scripts.compact_fresh_schema import load_compact_plan
from scripts.schema_assembly import validate_schema_assembly
from scripts.verify_validation_schema_manifest import load_manifest
from shared_kernel.migration_release import load_migration_release_manifest

ROOT = Path(__file__).resolve().parents[8]
PURPOSE = "1071_controlled_signed_staff_agreement.sql"
MEDIA = "1072_line_media_controlled_file_reference.sql"
MANIFEST = ROOT / "db/migration_releases/labor_union_2026_11_06_controlled_purpose_media_reference_v1.json"
TABLES = ("controlled_file_staging_objects", "controlled_file_objects")


def _snapshot(descriptor):
    """Plain metadata input for the existing comparator; no SQL driver is involved."""
    return {
        "columns": [
            {"table_name": table, "column_name": name, **contract}
            for table, columns in {
                **descriptor["tables"], **descriptor["parent_columns"],
            }.items()
            for name, contract in columns.items()
        ],
        "indexes": [
            {"table_name": table, "index_name": name,
             "non_unique": contract["non_unique"], "columns": ",".join(contract["columns"])}
            for (table, name), contract in descriptor["indexes"].items()
        ],
        "constraints": [
            {"table_name": table, "constraint_name": name,
             "constraint_type": "CHECK", "enforced": "YES", "check_clause": clause}
            for (table, name), clause in descriptor["checks"].items()
        ] + [
            {"table_name": table, "constraint_name": name, "constraint_type": "FOREIGN KEY"}
            for table, name in descriptor["foreign_keys"]
        ],
        "key_columns": [
            {"table_name": table, "constraint_name": name, "column_name": column,
             "referenced_table_name": contract["referenced_table"],
             "referenced_column_name": referenced}
            for (table, name), contract in descriptor["foreign_keys"].items()
            for column, referenced in zip(contract["columns"], contract["referenced_columns"])
        ],
        "foreign_keys": [
            {"table_name": table, "constraint_name": name,
             "update_rule": contract["update_rule"], "delete_rule": contract["delete_rule"]}
            for (table, name), contract in descriptor["foreign_keys"].items()
        ],
        "triggers": [
            {"trigger_name": name, **contract}
            for name, contract in descriptor["triggers"].items()
        ],
        "show_create_tables": {}, "views": [],
    }



def test_hash_bound_successors_are_selected_without_backfill():
    release = load_migration_release_manifest(MANIFEST, ROOT)
    assert migration.DEFAULT_RELEASE_MANIFESTS[-1] == MANIFEST.name
    assert migration.RELEASE_MANIFEST.release_id == release.release_id
    assert release.backfills == ()
    for name, released in release.owned_object_descriptors(ROOT).items():
        canonical = migration._canonical_artifact_descriptor(name)
        assert {k: v for k, v in released.items() if k != "triggers"} == {
            k: v for k, v in canonical.items() if k != "triggers"
        }
        assert released["triggers"] == set(canonical["triggers"])


def test_staff_purpose_appends_enum_and_preserves_all_guards_and_lineage():
    original = migration._canonical_artifact_descriptor("1005_contract_external_signing_successor.sql")
    successor = migration._canonical_artifact_descriptor(PURPOSE)
    foundation = migration._canonical_artifact_descriptor("1004_controlled_file_storage_foundation.sql")
    for table in TABLES:
        prior = original["parent_columns"][table]["purpose"]["column_type"]
        assert successor["parent_columns"][table]["purpose"]["column_type"] == prior[:-1] + ",'signed_staff_agreement')"
        assert successor["parent_columns"][table].keys() == foundation["tables"][table].keys()
    assert successor["triggers"] == {
        key: value for key, value in foundation["triggers"].items()
        if value["event_object_table"] in TABLES
    }
    fk = ("controlled_file_objects", "fk_controlled_file_object_supersedes")
    assert successor["foreign_keys"][fk] == original["foreign_keys"][fk]
    statements = migration.split_sql((ROOT / "db/schema_parts" / PURPOSE).read_text())
    assert len(statements) == 4
    assert migration._local_classify_statement(statements[0]) == "controlled_signed_staff_purpose_successor"
    assert migration._local_classify_statement(statements[2]) == "controlled_signed_staff_purpose_successor"
    previous = migration.split_sql((ROOT / "db/schema_parts" / "1005_contract_external_signing_successor.sql").read_text())
    assert statements[1] == previous[1]
    assert statements[3] == previous[3]
    with pytest.raises(migration.LocalAdditiveBlocked, match="noncanonical"):
        migration._local_classify_statement(statements[0].replace("'contract_signing'", "'staff'"))


def test_exact_purpose_predecessor_and_successor_only_with_intact_contracts():
    successor = migration._canonical_artifact_descriptor(PURPOSE)
    current = _snapshot(successor)
    assert migration.local_additive_descriptor_state(current, successor, PURPOSE) == "exact"
    prior = deepcopy(successor)
    original = migration._canonical_artifact_descriptor("1005_contract_external_signing_successor.sql")
    for table in TABLES:
        prior["parent_columns"][table]["purpose"] = original["parent_columns"][table]["purpose"]
    for key in prior["checks"]:
        if key in original["checks"]:
            prior["checks"][key] = original["checks"][key]
    assert migration.local_additive_descriptor_state(_snapshot(prior), successor, PURPOSE) == "absent"
    for missing in ("chk_controlled_file_staging_owner_purpose", "fk_controlled_file_object_supersedes"):
        damaged = deepcopy(current)
        damaged["constraints"] = [row for row in damaged["constraints"] if row["constraint_name"] != missing]
        assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) in {"partial", "drift"}
    damaged = deepcopy(current)
    damaged["triggers"] = damaged["triggers"][1:]
    assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) == "partial"
    damaged = deepcopy(current)
    next(row for row in damaged["columns"] if row["column_name"] == "purpose")["column_type"] = original["parent_columns"][TABLES[0]]["purpose"]["column_type"]
    assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) == "drift"
    damaged = deepcopy(current)
    damaged["columns"].append({**damaged["columns"][0], "column_name": "unreleased_column"})
    assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) == "drift"
    damaged = deepcopy(current)
    damaged["triggers"].append({**damaged["triggers"][0], "trigger_name": "unreleased_guard"})
    assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) == "drift"
    for clause in ("owner_type='staff'", "TRUE"):
        damaged = deepcopy(current)
        next(row for row in damaged["constraints"] if row["constraint_name"] == "chk_controlled_file_object_owner_purpose")["check_clause"] = clause
        assert migration.local_additive_descriptor_state(damaged, successor, PURPOSE) == "drift"


def test_foundation_and_external_signing_accept_only_selected_exact_successor():
    successor = migration._canonical_artifact_descriptor(PURPOSE)
    for name in ("1004_controlled_file_storage_foundation.sql", "1005_contract_external_signing_successor.sql"):
        original = migration._canonical_artifact_descriptor(name)
        current = deepcopy(original)
        for table in TABLES:
            target = current["tables"].get(table, current["parent_columns"].get(table))
            target["purpose"] = deepcopy(successor["parent_columns"][table]["purpose"])
        current["checks"].update({key: value for key, value in successor["checks"].items() if key[1].endswith("_owner_purpose")})
        assert migration.local_additive_descriptor_state(_snapshot(current), original, name) == "exact"
        damaged = _snapshot(current)
        next(row for row in damaged["columns"] if row["column_name"] == "purpose")["column_type"] = "varchar(191)"
        assert migration.local_additive_descriptor_state(damaged, original, name) == "drift"


def test_media_nullable_unsigned_exact_fk_and_legacy_predecessor():
    descriptor = migration._canonical_artifact_descriptor(MEDIA)
    column = descriptor["parent_columns"]["media_assets"]["controlled_file_object_id"]
    assert column == {"column_type": "bigint unsigned", "is_nullable": "YES", "column_default": None, "extra": ""}
    assert descriptor["foreign_keys"][("media_assets", "fk_media_controlled_file_object")] == {
        "columns": ("controlled_file_object_id",), "referenced_table": "controlled_file_objects",
        "referenced_columns": ("id",), "update_rule": "RESTRICT", "delete_rule": "RESTRICT",
    }
    current = _snapshot(descriptor)
    assert migration.local_additive_descriptor_state(current, descriptor, MEDIA) == "exact"
    prior = deepcopy(descriptor)
    prior["parent_columns"]["media_assets"].pop("controlled_file_object_id")
    prior["indexes"].pop(("media_assets", "idx_media_controlled_file_object"))
    prior["foreign_keys"].pop(("media_assets", "fk_media_controlled_file_object"))
    assert migration.local_additive_descriptor_state(_snapshot(prior), descriptor, MEDIA) == "absent"
    half = deepcopy(current)
    half["columns"] = [row for row in half["columns"] if row["column_name"] != "controlled_file_object_id"]
    assert migration.local_additive_descriptor_state(half, descriptor, MEDIA) == "drift"
    damaged = deepcopy(current)
    damaged["indexes"].append({"table_name": "media_assets", "index_name": "unexpected_index", "non_unique": 1, "columns": "storage_key"})
    assert migration.local_additive_descriptor_state(damaged, descriptor, MEDIA) == "drift"
    for field, value in (("column_type", "bigint"), ("is_nullable", "NO")):
        damaged = deepcopy(current)
        next(row for row in damaged["columns"] if row["column_name"] == "controlled_file_object_id")[field] = value
        assert migration.local_additive_descriptor_state(damaged, descriptor, MEDIA) == "drift"
    for missing in ("idx_media_controlled_file_object", "fk_media_controlled_file_object", "fk_media_created_by"):
        damaged = deepcopy(current)
        damaged["indexes"] = [row for row in damaged["indexes"] if row["index_name"] != missing]
        damaged["constraints"] = [row for row in damaged["constraints"] if row["constraint_name"] != missing]
        assert migration.local_additive_descriptor_state(damaged, descriptor, MEDIA) in {"partial", "drift"}


def test_current_text_full_release_and_compact_bind_same_contracts():
    assert validate_schema_assembly() == []
    assert verify_release(load_manifest()) == []
    plan = load_compact_plan()
    for table in TABLES:
        sql, = (step["sql"] for step in plan["steps"] if step["sql"].startswith(f"CREATE TABLE `{table}`"))
        checks = migration._show_create_check_clauses(sql)
        canonical = migration._canonical_artifact_descriptor(PURPOSE)
        for key, clause in canonical["checks"].items():
            if key[0] == table:
                assert migration._normalize_check_contract(checks[key]) == migration._normalize_check_contract(clause)
        assert "'rich_menu_background','signed_staff_agreement')" in sql
    media, = (step["sql"] for step in plan["steps"] if step["sql"].startswith("CREATE TABLE `media_assets`"))
    assert "`controlled_file_object_id` bigint unsigned DEFAULT NULL" in media
    assert "CONSTRAINT `fk_media_controlled_file_object`" in media
