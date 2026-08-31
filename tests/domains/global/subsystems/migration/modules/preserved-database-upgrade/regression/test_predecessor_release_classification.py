from __future__ import annotations

from scripts import migrate_preserved_database_additive_schema as migration


ARTIFACT = "1005_contract_external_signing_successor.sql"


def _empty_snapshot() -> dict[str, list[object] | dict[str, object]]:
    return {
        "columns": [],
        "indexes": [],
        "constraints": [],
        "key_columns": [],
        "foreign_keys": [],
        "triggers": [],
        "show_create_tables": {},
        "views": [],
    }


def test_contract_successor_accepts_exact_pre_1004_dependency_as_absent() -> None:
    descriptor = migration._canonical_artifact_descriptor(ARTIFACT)
    snapshot = _empty_snapshot()

    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ARTIFACT
    ) == "absent"

    snapshot["columns"].append({
        "table_name": "controlled_file_objects",
        "column_name": "purpose",
        "column_type": descriptor["parent_columns"]
        ["controlled_file_objects"]["purpose"]["column_type"],
        "is_nullable": "NO",
        "column_default": None,
        "extra": "",
    })
    assert migration.local_additive_descriptor_state(
        snapshot, descriptor, ARTIFACT
    ) == "drift"
