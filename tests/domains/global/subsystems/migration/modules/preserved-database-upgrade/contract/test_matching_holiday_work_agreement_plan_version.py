"""Contract coverage for the holiday-work agreement plan-version rename."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts import migrate_preserved_database_additive_schema as migration
from shared_kernel.migration_release import load_migration_release_manifest


ROOT = Path(__file__).resolve().parents[8]
OWNER_ARTIFACT = "1032_matching_holiday_work_agreements.sql"
RENAME_ARTIFACT = "1033_matching_holiday_work_agreements.sql"
OWNER_MANIFEST = "labor_union_2026_09_07_matching_holiday_work_agreements_v1.json"
RENAME_MANIFEST = (
    "labor_union_2026_09_08_matching_holiday_work_agreement_plan_version_v1.json"
)


def _canonical_owner_snapshot() -> dict[str, object]:
    descriptor = migration._canonical_artifact_descriptor(OWNER_ARTIFACT)
    columns = []
    for table, contracts in {
        **descriptor["tables"],
        **descriptor["parent_columns"],
    }.items():
        for column, contract in contracts.items():
            columns.append({
                "table_name": table,
                "column_name": column,
                **contract,
            })
    indexes = [
        {
            "table_name": table,
            "index_name": name,
            "non_unique": contract["non_unique"],
            "columns": ",".join(contract["columns"]),
        }
        for (table, name), contract in descriptor["indexes"].items()
    ]
    constraints = []
    key_columns = []
    foreign_keys = []
    for (table, name), contract in descriptor["foreign_keys"].items():
        constraints.append({
            "table_name": table,
            "constraint_name": name,
            "constraint_type": "FOREIGN KEY",
        })
        foreign_keys.append({
            "table_name": table,
            "constraint_name": name,
            "update_rule": contract["update_rule"],
            "delete_rule": contract["delete_rule"],
        })
        key_columns.extend({
            "table_name": table,
            "constraint_name": name,
            "column_name": column,
            "referenced_table_name": contract["referenced_table"],
            "referenced_column_name": referenced,
        } for column, referenced in zip(
            contract["columns"], contract["referenced_columns"], strict=True
        ))
    constraints.extend({
        "table_name": table,
        "constraint_name": name,
        "constraint_type": "CHECK",
        "check_clause": contract,
        "enforced": "YES",
    } for (table, name), contract in descriptor["checks"].items())
    triggers = [
        {"trigger_name": name, **contract}
        for name, contract in descriptor["triggers"].items()
    ]
    return {
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "triggers": triggers,
        "show_create_tables": {},
        "views": [],
    }


def _legacy_predecessor_snapshot() -> dict[str, object]:
    snapshot = deepcopy(_canonical_owner_snapshot())
    for row in snapshot["columns"]:
        if (
            row["table_name"] == "matching_holiday_work_agreements"
            and row["column_name"] == "plan_version"
        ):
            row["column_name"] = "plan_communication_version"
    for row in snapshot["indexes"]:
        if row["table_name"] == "matching_holiday_work_agreements":
            row["columns"] = row["columns"].replace(
                "plan_version", "plan_communication_version"
            )
    return snapshot


def test_plan_version_release_is_ordered_hash_bound_and_migration_only() -> None:
    configured = migration.DEFAULT_RELEASE_MANIFESTS
    assert configured[configured.index(OWNER_MANIFEST) + 1] == RENAME_MANIFEST

    manifest = load_migration_release_manifest(
        ROOT / "db/migration_releases" / RENAME_MANIFEST,
        ROOT,
    )
    assert manifest.schema_paths(ROOT) == (
        (ROOT / "db/schema_parts" / RENAME_ARTIFACT).resolve(),
    )
    assert manifest.backfills == ()
    released = manifest.owned_object_descriptors(ROOT)[RENAME_ARTIFACT]
    canonical = migration._canonical_artifact_descriptor(RENAME_ARTIFACT)
    assert released["parent_columns"] == canonical["parent_columns"]
    statements = migration.split_sql(
        (ROOT / "db/schema_parts" / RENAME_ARTIFACT).read_text(encoding="utf-8")
    )
    assert len(statements) == 1
    assert migration._local_classify_statement(statements[0]) == (
        "matching_holiday_work_agreement_plan_version_rename"
    )


def test_owner_release_keeps_exact_immutable_check_encoding_compatible() -> None:
    owner = load_migration_release_manifest(
        ROOT / "db/migration_releases" / OWNER_MANIFEST,
        ROOT,
    )
    released = owner.owned_object_descriptors(ROOT)[OWNER_ARTIFACT]

    assert migration._release_descriptor_metadata_state(
        _canonical_owner_snapshot(), OWNER_ARTIFACT, released
    ) == "exact"


def test_plan_version_rename_accepts_only_the_exact_legacy_predecessor() -> None:
    owner = migration._canonical_artifact_descriptor(OWNER_ARTIFACT)
    rename = migration._canonical_artifact_descriptor(RENAME_ARTIFACT)
    predecessor = _legacy_predecessor_snapshot()

    assert migration.local_additive_descriptor_state(
        predecessor, owner, OWNER_ARTIFACT
    ) == "exact"
    assert migration.local_additive_descriptor_state(
        predecessor, rename, RENAME_ARTIFACT
    ) == "absent"

    successor = _canonical_owner_snapshot()
    assert migration.local_additive_descriptor_state(
        successor, owner, OWNER_ARTIFACT
    ) == "exact"
    assert migration.local_additive_descriptor_state(
        successor, rename, RENAME_ARTIFACT
    ) == "exact"

    legacy_column = next(
        row for row in predecessor["columns"]
        if row["column_name"] == "plan_communication_version"
    )
    legacy_column["column_type"] = "bigint unsigned"
    assert migration.local_additive_descriptor_state(
        predecessor, owner, OWNER_ARTIFACT
    ) == "drift"


def test_plan_version_rename_preservation_compares_the_legacy_projection(
    monkeypatch,
) -> None:
    calls = []

    def projection(_config, database, table, columns, **kwargs):
        calls.append((database, table, columns, kwargs))
        return {"columns": columns, "row_count": 1, "rows_sha256": "same"}

    monkeypatch.setattr(migration, "_table_projection_evidence", projection)
    source_snapshot = {
        "columns": [
            {
                "table_name": "matching_holiday_work_agreements",
                "column_name": name,
            }
            for name in ("id", "plan_communication_version")
        ]
    }

    result = migration._verify_matching_holiday_work_agreement_plan_version_rename(
        object(), "source", "candidate", source_snapshot
    )

    assert result["row_count"] == 1
    assert calls[0][3] == {}
    assert calls[1][3] == {
        "column_sources": {"plan_communication_version": "plan_version"}
    }
